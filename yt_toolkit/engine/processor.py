import cv2
import mediapipe as mp
import os
import logging
import numpy as np
import subprocess
import yaml
from pathlib import Path
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Import utilitas umum
from yt_toolkit.core.utils import get_duration, run_ffmpeg_with_progress, suppress_stderr, FFmpegPipeWriter, setup_paths, get_common_ffmpeg_args

class UniversalRenderer:
    """
    Renderer universal yang menggabungkan logika Tracking (Monologue) dan Split Screen (Podcast).
    - 0-1 Wajah: Tracking Mode (Zoom & Follow).
    - 2+ Wajah: Split Screen Mode (Atas/Bawah).
    """
    def __init__(self, processor):
        self.processor = processor
        self.prev_centers = {}
        self.w_in = 0
        self.h_in = 0
        self.target_w = 0
        self.target_h = 0
        self.fps = 30.0
        self.last_timestamp_ms = -1
        
        # Optimization State (Prioritas 3)
        self.roi = None # (x, y, w, h)
        self.frames_since_detection = 999
        self.current_skip_interval = 3
        
        # Tracking State (Monologue)
        self.anchor = None
        self.transition_val = 0.0
        self.last_target_x = 0
        self.faces = []
        self.current_movement_speed = 0.0
        self.zoom_out_factor = 0.0
        
    def setup(self, w_in, h_in, target_w, target_h, fps):
        self.w_in = w_in
        self.h_in = h_in
        self.target_w = target_w
        self.target_h = target_h
        self.fps = fps
        self.last_target_x = w_in // 2
        self.last_timestamp_ms = -1
        self.current_skip_interval = self.processor.base_skip_interval

        if not self.processor.detector:
            self.processor._initialize_detector()

    def process_frame(self, frame, frame_count) -> list:
        # 1. DETEKSI WAJAH
        self.frames_since_detection += 1
        is_detection_frame = (self.frames_since_detection >= self.current_skip_interval)
        
        if is_detection_frame:
            self.faces = self._detect_faces(frame, frame_count)
            self.faces.sort(key=lambda f: f['x'])
            self.frames_since_detection = 0
            
            # Adaptive Skipping: Jika gerakan cepat (>0.5% layar/frame), scan tiap frame
            if self.current_movement_speed > 0.005:
                self.current_skip_interval = 1
            else:
                self.current_skip_interval = self.processor.base_skip_interval

        # 2. CABANG LOGIKA
        return self._render_tracking(frame, is_detection_frame)

    def flush(self) -> list:
        return []

    def _detect_faces(self, frame, frame_count):
        # Helper timestamp MediaPipe
        timestamp_ms = int((frame_count * 1000) / self.fps)
        if timestamp_ms <= self.last_timestamp_ms: timestamp_ms = self.last_timestamp_ms + 1
        self.last_timestamp_ms = timestamp_ms

        detected_faces = []
        img_h, img_w = frame.shape[:2]

        # A. ROI DETECTION (Optimasi)
        if self.processor.enable_roi and self.roi:
            rx, ry, rw, rh = self.roi
            # Clamp ROI agar tidak keluar batas gambar
            rx = max(0, rx); ry = max(0, ry)
            rw = min(rw, img_w - rx); rh = min(rh, img_h - ry)
            
            if rw > 20 and rh > 20: # Pastikan ROI valid
                crop = frame[ry:ry+rh, rx:rx+rw]
                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
                
                result = self.processor.detector.detect_for_video(mp_crop, timestamp_ms)
                
                if result.detections:
                    for det in result.detections:
                        bbox = det.bounding_box
                        # Translate koordinat crop kembali ke full frame
                        global_x = bbox.origin_x + rx
                        global_y = bbox.origin_y + ry
                        
                        area = bbox.width * bbox.height
                        center_x = int(global_x + bbox.width / 2)
                        center_y = int(global_y + bbox.height / 2)
                        detected_faces.append({'area': area, 'x': center_x, 'y': center_y, 'w': bbox.width, 'h': bbox.height})
                    
                    # Update ROI (Center on face, 3x size)
                    main = max(detected_faces, key=lambda f: f['area'])
                    roi_w = int(main['w'] * 3)
                    roi_h = int(main['h'] * 3)
                    self.roi = (int(main['x'] - roi_w/2), int(main['y'] - roi_h/2), roi_w, roi_h)
                    return detected_faces
                else:
                    # ROI gagal, reset ke full frame (fallback)
                    self.roi = None

        # B. FULL FRAME DETECTION (Standard)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.processor.detector.detect_for_video(mp_image, timestamp_ms)
        
        if result.detections:
            for det in result.detections:
                bbox = det.bounding_box
                area = bbox.width * bbox.height
                center_x = int(bbox.origin_x + bbox.width / 2)
                center_y = int(bbox.origin_y + bbox.height / 2)
                detected_faces.append({'area': area, 'x': center_x, 'y': center_y, 'w': bbox.width, 'h': bbox.height})
            
            # Set Initial ROI
            main = max(detected_faces, key=lambda f: f['area'])
            roi_w = int(main['w'] * 3)
            roi_h = int(main['h'] * 3)
            self.roi = (int(main['x'] - roi_w/2), int(main['y'] - roi_h/2), roi_w, roi_h)
            
        return detected_faces

    def _get_smooth_x(self, face_id, target_x):
        if face_id not in self.prev_centers:
            self.prev_centers[face_id] = target_x
            return target_x
        prev_x = self.prev_centers[face_id]
        diff = abs(target_x - prev_x)
        speed_boost = min(diff, self.processor.SMOOTHING_MAX_DIFF) / self.processor.SMOOTHING_MAX_DIFF * self.processor.SMOOTHING_BOOST_FACTOR
        current_factor = self.processor.SMOOTHING_BASE_FACTOR + speed_boost 
        self.prev_centers[face_id] = int((1 - current_factor) * prev_x + current_factor * target_x)
        return self.prev_centers[face_id]

    def _render_tracking(self, frame, is_detection_frame):
        target_mode = "CINEMATIC"
        target_x = self.w_in // 2
        max_face_ratio = 0.0
        
        if self.faces:
            # Use largest face
            main_face = max(self.faces, key=lambda f: f['area'])
            max_face_ratio = main_face['area'] / (self.w_in * self.h_in)
            is_big_enough = (main_face['area'] / (self.w_in * self.h_in)) > self.processor.MIN_FACE_AREA_RATIO
            
            if self.anchor:
                size_diff = abs(main_face['area'] - self.anchor['size']) / self.anchor['size']
                if size_diff < self.processor.ANCHOR_SIZE_TOLERANCE:
                    self.anchor['size'] = self.anchor['size'] * 0.9 + main_face['area'] * 0.1
                    self.anchor['x'] = main_face['x']
                    target_mode = "TRACKING"
                    target_x = main_face['x']
                else:
                    if is_big_enough:
                        self.anchor = {'size': main_face['area'], 'x': main_face['x']}
                        target_mode = "TRACKING"
                        target_x = main_face['x']
                        # Reset smoothing for main face if anchor changes drastically
                        if 'main' in self.prev_centers: del self.prev_centers['main']
                    else:
                        target_mode = "CINEMATIC"
            else:
                if is_big_enough:
                    self.anchor = {'size': main_face['area'], 'x': main_face['x']}
                    target_mode = "TRACKING"
                    target_x = main_face['x']
                else:
                    target_mode = "CINEMATIC"

        if is_detection_frame:
            # Hitung kecepatan relatif terhadap interval skip aktual
            interval = max(1, self.current_skip_interval)
            self.current_movement_speed = (abs(target_x - self.last_target_x) / self.w_in) / interval
            self.last_target_x = target_x

        dynamic_zoom_speed = self.processor.TRANSITION_SPEED + (self.current_movement_speed * 1.5)

        if target_mode == "CINEMATIC":
            self.transition_val = min(1.0, self.transition_val + self.processor.TRANSITION_SPEED)
        else:
            self.transition_val = max(0.0, self.transition_val - dynamic_zoom_speed)

        # --- LOGIKA AUTO-ZOOM OUT (CLOSE-UP PROTECTION) ---
        # Jika wajah > 13% layar, kita zoom out perlahan agar tidak terlalu penuh.
        target_zoom = 0.0
        if max_face_ratio > 0.13:
            target_zoom = min(0.8, (max_face_ratio - 0.13) * 3.5)
        
        # Smoothing zoom out agar tidak memompa (pumping)
        if target_zoom > self.zoom_out_factor:
            self.zoom_out_factor += 0.01
        else:
            self.zoom_out_factor -= 0.02
        self.zoom_out_factor = np.clip(self.zoom_out_factor, 0.0, 0.8)

        final_target_x = target_x if self.transition_val < 0.9 else (self.w_in // 2)
        smooth_x = self._get_smooth_x('main', final_target_x)
        
        base_view_w = self.target_w + (self.w_in - self.target_w) * self.transition_val
        current_view_w = base_view_w + (self.w_in - base_view_w) * self.zoom_out_factor
        current_center_x = smooth_x + ((self.w_in // 2) - smooth_x) * self.transition_val
        
        crop_w = int(current_view_w)
        x1 = int(current_center_x - crop_w // 2)
        x1 = np.clip(x1, 0, self.w_in - crop_w)
        
        crop_img = frame[0:self.h_in, x1:x1+crop_w]
        scale = self.target_w / crop_w
        new_h = int(self.h_in * scale)
        resized_img = cv2.resize(crop_img, (self.target_w, new_h), interpolation=cv2.INTER_AREA)
        
        final_frame = np.zeros((self.target_h, self.target_w, 3), dtype=np.uint8)
        
        if new_h >= self.target_h:
            y_off = (new_h - self.target_h) // 2
            final_frame = resized_img[y_off:y_off+self.target_h, :]
        else:
            # Fill background with average color
            avg_pixel = cv2.resize(frame, (1, 1), interpolation=cv2.INTER_AREA)
            b, g, r = avg_pixel[0][0]
            final_frame[:] = (int(b * 0.3), int(g * 0.3), int(r * 0.3))
            y_pos = (self.target_h - new_h) // 2
            final_frame[y_pos:y_pos+new_h, :] = resized_img

        return [final_frame]

class VideoProcessor:
    """
    Class untuk memproses visual video.
    Menggunakan Universal Renderer untuk mengubah format landscape ke portrait (9:16)
    dengan fitur Smart Tracking otomatis.
    """
    def __init__(self, model_path=None, use_gpu=False):
        """
        Inisialisasi Face Tracker menggunakan MediaPipe Tasks API.
        """
        # Pastikan model .tflite ada di path yang ditentukan (folder models)
        if model_path is None:
            model_path = str(setup_paths().DETECTOR_MODEL_PATH)
            
        if not os.path.exists(model_path):
            logging.error(f"Model {model_path} tidak ditemukan!")
            raise FileNotFoundError(f"Silakan unduh detector.tflite dari MediaPipe.")
            
        self.model_path = model_path
        self.use_gpu = use_gpu
        self.detector = None

        # --- KONFIGURASI ALGORITMA ---
        # Konfigurasi Monologue Mode (Face Tracking)
        self.SMOOTHING_BASE_FACTOR = 0.02  # Faktor kehalusan dasar (kamera lambat).
        self.SMOOTHING_BOOST_FACTOR = 0.15 # Faktor kehalusan tambahan saat subjek bergerak cepat.
        self.SMOOTHING_MAX_DIFF = 200.0    # Jarak maksimal untuk menghitung boost.

        # Konfigurasi Hybrid Engine (Monologue)
        self.TRANSITION_SPEED = 0.05       # Kecepatan transisi Zoom (0.05 = ~20 frame)
        self.ANCHOR_SIZE_TOLERANCE = 0.45  # [MODIFIKASI] Toleransi lebih longgar untuk Frame Skipping
        self.MIN_FACE_AREA_RATIO = 0.04    # Wajah harus minimal 4% dari layar untuk dianggap Anchor valid
        
        # Load Config untuk Optimasi (Prioritas 3)
        self.enable_roi = True
        self.base_skip_interval = 3
        try:
            with open(setup_paths().CONFIG_FILE, 'r') as f:
                cfg = yaml.safe_load(f)
                self.enable_roi = cfg.get('face_tracking_roi', True)
                self.base_skip_interval = cfg.get('face_tracking_skip_frames', 3)
        except Exception:
            pass

        # --- Variabel State (direset per video) ---
    
    def __enter__(self):
        """Memungkinkan penggunaan 'with VideoProcessor(...) as proc:'"""
        return self

    def __exit__(self, *args):
        """Otomatis menutup resource saat keluar dari blok 'with'."""
        self.close()

    def _initialize_detector(self):
        """
        Menginisialisasi detector MediaPipe dengan fallback otomatis dari GPU ke CPU.
        Ini mencegah duplikasi kode di setiap fungsi proses.
        """
        # 1. Coba inisialisasi dengan GPU jika diminta oleh pengguna.
        if self.use_gpu:
            try:
                logging.info("Mencoba inisialisasi MediaPipe dengan delegasi GPU...")
                options = vision.FaceDetectorOptions(
                    base_options=python.BaseOptions(model_asset_path=self.model_path, delegate=python.BaseOptions.Delegate.GPU),
                    running_mode=vision.RunningMode.VIDEO,
                    min_detection_confidence=0.6
                )
                with suppress_stderr(): # Sembunyikan log C++ yang 'berisik' dari TensorFlow.
                    self.detector = vision.FaceDetector.create_from_options(options)
                logging.info("✅ MediaPipe berhasil dimuat di GPU.")
                return # Berhasil, keluar dari fungsi.
            except Exception as e:
                logging.warning(f"⚠️ Inisialisasi MediaPipe GPU gagal, beralih ke CPU. Error: {e}")
                self.detector = None # Pastikan detector direset jika GPU gagal.

        # 2. Jika GPU tidak diminta atau gagal, gunakan CPU sebagai fallback.
        logging.info("Menginisialisasi MediaPipe dengan delegasi CPU...")
        options = vision.FaceDetectorOptions(
            base_options=python.BaseOptions(model_asset_path=self.model_path, delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO,
            min_detection_confidence=0.6
        )
        with suppress_stderr():
            self.detector = vision.FaceDetector.create_from_options(options)
        logging.info("✅ MediaPipe berhasil dimuat di CPU.")

    def _process_loop(self, cap, out, renderer, total_frames, progress_callback, resize_dim=None):
        """Engine utama yang menjalankan loop pemrosesan frame."""
        frame_count = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret: break
                
                # [OPTIMASI RAM] Resize di awal jika diminta
                if resize_dim:
                    frame = cv2.resize(frame, resize_dim, interpolation=cv2.INTER_AREA)
                
                # Delegasikan logika visual ke Strategy aktif
                output_frames = renderer.process_frame(frame, frame_count)
                
                for f in output_frames:
                    out.write(f)
                    
                frame_count += 1
                if progress_callback and total_frames > 0:
                    progress_callback((frame_count / total_frames) * 100, "Processing")
            
            # Flush sisa buffer (penting untuk Podcast mode)
            for f in renderer.flush():
                out.write(f)
                
        finally:
            pass

    def process_video(self, input_path: str, output_path: str, progress_callback=None, subtitle_path=None, fonts_dir=None):
        """
        Memproses video menggunakan Universal Renderer (9:16).
        Membuka, menulis, menutup file, dan menggabungkan audio.
        """
        # Tutup dan reset detector yang ada sebelum memproses klip baru untuk mereset timestamp.
        self.close()

        # Gunakan VideoCapture standar (lebih sederhana dan stabil)
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logging.error(f"Gagal membuka video: {input_path}")
            return False

        # Baca properti dasar
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # [OPTIMASI RAM] Input Resolution Capping
        # Jika video > 1080p (misal 4K), resize di awal untuk menghemat RAM & CPU.
        resize_dim = None
        MAX_DIMENSION = 1920
        if max(w, h) > MAX_DIMENSION:
            scale_factor = MAX_DIMENSION / max(w, h)
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            resize_dim = (new_w, new_h)
            logging.info(f"Input Capping: {w}x{h} -> {new_w}x{new_h} (Scale: {scale_factor:.2f})")
            w, h = new_w, new_h

        # [FIX SYNC] Hitung FPS presisi berdasarkan durasi asli untuk mengatasi VFR drift
        # OpenCV seringkali salah membaca FPS metadata pada video VFR, menyebabkan audio drift.
        # Kita paksa FPS output agar durasi video visual == durasi audio asli.
        try:
            real_duration = get_duration(input_path)
            if real_duration > 0 and total_frames > 0:
                calc_fps = total_frames / real_duration
                # Gunakan calculated FPS jika valid (sanity check antara 5-120 fps)
                if 5 < calc_fps < 120:
                    logging.info(f"Sync Correction: Metadata FPS={fps:.4f} -> Real FPS={calc_fps:.4f}")
                    fps = calc_fps
        except Exception:
            pass

        # Dapatkan resolusi target (9:16)
        target_h = h
        target_w = int(h * 9 / 16)
        
        # Inisialisasi Renderer Strategy
        renderer = UniversalRenderer(self)
        renderer.setup(w, h, target_w, target_h, fps)

        # Konfigurasi Filter FFmpeg (Subtitles)
        # Jika subtitle_path ada, kita gunakan filter_complex. Jika tidak, map biasa.
        ffmpeg_input_args = ['-i', '-', '-i', input_path]
        ffmpeg_map_args = []
        
        if subtitle_path and os.path.exists(subtitle_path):
            # Escape path untuk Windows (FFmpeg filter requirement)
            clean_ass = str(subtitle_path).replace('\\', '\\\\').replace(':', '\\:')
            clean_fonts = str(fonts_dir).replace('\\', '\\\\').replace(':', '\\:') if fonts_dir else ''
            
            # [0:v] adalah input raw video dari pipe. Kita burn subtitle ke situ.
            ffmpeg_map_args = [
                '-filter_complex', f"[0:v]subtitles=filename='{clean_ass}':fontsdir='{clean_fonts}'[v]",
                '-map', '[v]',       # Gunakan output filter [v] sebagai video stream
                '-map', '1:a:0'      # Ambil audio dari input 1
            ]
        else:
            ffmpeg_map_args = [
                '-map', '0:v:0',
                '-map', '1:a:0'
            ]

        # [SINGLE-PASS] Setup FFmpeg Command untuk encoding langsung dari pipe
        cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{target_w}x{target_h}',
            '-pix_fmt', 'bgr24',
            '-r', f'{fps:.4f}',
            *ffmpeg_input_args,
            *ffmpeg_map_args,
            *get_common_ffmpeg_args(),
            '-c:a', 'copy',
            '-shortest',
            output_path
        ]

        out = FFmpegPipeWriter(cmd)

        try:
            self._process_loop(cap, out, renderer, total_frames, progress_callback, resize_dim)
            return True
            
        except Exception as e:
            logging.error(f"Error selama pemrosesan video: {e}", exc_info=True)
            return False
        finally:
            # Pastikan semua resource dilepaskan
            cap.release()
            out.release()

    def add_audio(self, video_visual_path, audio_source_path, final_output_path, progress_callback=None):
        """
        Menggabungkan visual hasil crop dengan audio dari file asli menggunakan FFmpeg.
        """
        v_path = str(Path(video_visual_path).resolve())
        a_path = str(Path(audio_source_path).resolve())
        o_path = str(Path(final_output_path).resolve())
        
        # Pastikan folder output sudah ada
        os.makedirs(os.path.dirname(o_path), exist_ok=True)
        # Kita gunakan perintah FFmpeg: ambil video dari visual_path, ambil audio dari audio_source
        cmd = [
            "ffmpeg", '-y',
            '-i', v_path,    # Input 0: Video tanpa suara
            '-i', a_path,    # Input 1: Video asli (sumber audio)
            '-c:v', 'copy',
            '-c:a', 'copy',             # Audio sudah bersih dari downloader, cukup copy
            '-map_metadata', '-1',
            '-map', '0:v:0',            # Ambil video dari input 0
            '-map', '1:a:0',            # Ambil audio dari input 1
            '-shortest',
            o_path
        ]
        try:
            duration = get_duration(v_path)
            run_ffmpeg_with_progress(cmd, duration, "Menggabungkan audio", progress_callback)
            # Hapus file sementara yang tanpa suara jika berhasil
            if os.path.exists(v_path):
                try: os.remove(v_path)
                except OSError as e: logging.warning(f"Gagal menghapus file video sementara: {e}")
            return True
        except Exception as e:
            print(f"❌ Gagal menggabungkan audio: {e}")
            return False

    def close(self):
        if self.detector:
            self.detector.close()
            self.detector = None