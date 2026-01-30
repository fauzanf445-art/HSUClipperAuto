import cv2
import mediapipe as mp
import os
import sys
import logging
import numpy as np
import subprocess
import re
from pathlib import Path
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from typing import List
from collections import deque

# Import utilitas umum
from .utils import get_duration, run_ffmpeg_with_progress, suppress_stderr

class VideoProcessor:
    """
    Class untuk memproses visual video.
    - Mengubah format landscape ke portrait (9:16).
    - Menerapkan tracking wajah (Monologue Mode).
    - Menerapkan smart static camera (Podcast Mode).
    - Menerapkan efek blur background (Cinematic Mode).
    """
    def __init__(self, model_path='detector.tflite', ffmpeg_path='ffmpeg', ffprobe_path='ffprobe', use_gpu=False):
        """
        Inisialisasi Face Tracker menggunakan MediaPipe Tasks API.
        """
        # Pastikan model .tflite ada di path yang ditentukan (folder models)
        if not os.path.exists(model_path):
            logging.error(f"Model {model_path} tidak ditemukan!")
            raise FileNotFoundError(f"Silakan unduh detector.tflite dari MediaPipe.")
            
        self.model_path = model_path
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.use_gpu = use_gpu
        self.detector = None

        # --- KONFIGURASI ALGORITMA ---
        # Konfigurasi Umum
        self.LOOKAHEAD_RANGE = 6  # Jumlah frame masa depan yang diintip untuk pergerakan cerdas.
        self.SCENE_CUT_THRESHOLD_PX = 300  # Jarak perpindahan wajah (pixel) untuk dianggap scene cut.

        # Konfigurasi Monologue Mode (Face Tracking)
        self.SMOOTHING_BASE_FACTOR = 0.02  # Faktor kehalusan dasar (kamera lambat).
        self.SMOOTHING_BOOST_FACTOR = 0.15 # Faktor kehalusan tambahan saat subjek bergerak cepat.
        self.SMOOTHING_MAX_DIFF = 200.0    # Jarak maksimal untuk menghitung boost.
        self.MODE_BUFFER_SIZE = 30         # Jumlah frame untuk validasi perpindahan mode (1.5 detik @ 30fps).
        self.MODE_SWITCH_THRESHOLD = 0.7   # 70% frame di buffer harus konsisten untuk ganti mode.

        # Konfigurasi Podcast Mode (Smart Static)
        self.PODCAST_STABILITY_THRESHOLD = 20      # Jumlah frame subjek harus stabil sebelum kamera 'cut'.
        self.PODCAST_MOVEMENT_DEADZONE_RATIO = 0.20 # 20% dari lebar layar, gerakan di bawah ini diabaikan.
        self.PODCAST_SPLIT_ZOOM_FACTOR = 0.6       # Faktor zoom untuk mode split screen 2 orang.

        # Konfigurasi Cinematic Mode
        self.CINEMATIC_CROP_MARGIN = 0.15 # 15% crop dari setiap sisi untuk efek zoom.

        # --- Variabel State (direset per video) ---
        # Menyimpan posisi X terakhir untuk setiap ID wajah agar pergerakan kamera mulus.
        self.prev_centers = {} 
        # Buffer untuk logika 'Hysteresis' (mencegah kamera 'flickering' antar mode).
        self.mode_history = [] 
        self.current_mode = 1 # Mode aktif saat ini (1: Single, 2: Split)
    
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

    def _get_smooth_x(self, face_id, target_x):
        """Menghitung posisi X yang halus menggunakan LERP Adaptif (Dynamic Smoothing).
        - Jika target bergerak jauh, kamera merespons lebih cepat.
        - Jika target bergerak sedikit, kamera merespons lebih lambat (efek sinematik).
        """
        if face_id not in self.prev_centers:
            self.prev_centers[face_id] = target_x
            return target_x
            
        prev_x = self.prev_centers[face_id]
        diff = abs(target_x - prev_x)

        speed_boost = min(diff, self.SMOOTHING_MAX_DIFF) / self.SMOOTHING_MAX_DIFF * self.SMOOTHING_BOOST_FACTOR
        current_factor = self.SMOOTHING_BASE_FACTOR + speed_boost 
        
        self.prev_centers[face_id] = int((1 - current_factor) * prev_x + current_factor * target_x)
        return self.prev_centers[face_id]

    def _determine_mode(self, num_faces):
        """
        Menentukan mode tampilan (Single vs Split) dengan Sticky Logic.
        Hanya berpindah mode jika deteksi konsisten selama beberapa frame untuk mengurangi 'flickering'.
        """
        detected_mode = 2 if num_faces != 1 else 1
        self.mode_history.append(detected_mode)
        if len(self.mode_history) > self.MODE_BUFFER_SIZE:
            self.mode_history.pop(0)
        
        # Ambang batas stabilitas (misal 90% dari buffer harus konsisten untuk pindah)
        threshold = int(self.MODE_BUFFER_SIZE * self.MODE_SWITCH_THRESHOLD)
        
        if self.current_mode == 1:
            # Jika sedang Single, butuh bukti kuat untuk pindah ke Split
            if self.mode_history.count(2) >= threshold:
                self.current_mode = 2
        else:
            # Jika sedang Split, butuh bukti kuat untuk pindah ke Single
            if self.mode_history.count(1) >= threshold:
                self.current_mode = 1
                
        return self.current_mode

    def _portrait_logic(self, cap, out, w, h, fps):
        """Logika inti untuk Monologue Mode (Face Tracking)."""
        target_w = int(h * 9 / 16)

        self.prev_centers = {}
        self.mode_history = [] # Reset buffer untuk video baru
        self.current_mode = 1  # Reset mode ke default
        frame_count = 0 
        last_timestamp_ms = -1

        # Panggil helper untuk inisialisasi detector dengan fallback GPU->CPU.
        if not self.detector: self._initialize_detector()

        try:
            # --- LOOK-AHEAD SETUP ---
            lookahead_range = self.LOOKAHEAD_RANGE
            frame_buffer = deque() # Buffer untuk menyimpan {frame, faces_x, mode}
            last_face_x = None # Untuk mendeteksi Scene Cut (Perpindahan drastis)

            while True:
                # 1. FASE BACA & DETEKSI (Mengisi Buffer)
                ret, frame = cap.read()
                
                if ret:
                    # Konversi untuk MediaPipe
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                    # Hitung timestamp manual dan pastikan selalu naik untuk mencegah error MediaPipe.
                    timestamp_ms = int((frame_count * 1000) / fps) 
                    if timestamp_ms <= last_timestamp_ms:
                        timestamp_ms = last_timestamp_ms + 1
                    last_timestamp_ms = timestamp_ms

                    result = self.detector.detect_for_video(mp_image, timestamp_ms)

                    # Ambil semua pusat wajah yang terdeteksi
                    faces_x = []
                    if result.detections:
                        for det in result.detections:
                            bbox = det.bounding_box
                            faces_x.append(int(bbox.origin_x + (bbox.width / 2)))
                        faces_x.sort()

                    # --- DETEKSI SCENE CUT ---
                    # Jika posisi wajah utama melompat drastis (>300px), kemungkinan terjadi pergantian shot.
                    # Reset buffer dan smoothing untuk mencegah 'blending' antar shot yang berbeda.
                    current_face_x = faces_x[0] if faces_x else None
                    if last_face_x is not None and current_face_x is not None:
                        if abs(current_face_x - last_face_x) > self.SCENE_CUT_THRESHOLD_PX:
                            frame_buffer.clear()
                            self.prev_centers = {} # Reset smoothing state
                    
                    last_face_x = current_face_x

                    frame_buffer.append({'frame': frame, 'faces_x': faces_x})
                    frame_count += 1
                
                # 2. FASE RENDER (Hanya jika buffer penuh atau stream habis)
                # Kita butuh buffer terisi minimal 'lookahead_range' sebelum mulai render
                if len(frame_buffer) > lookahead_range or (not ret and frame_buffer):
                    
                    # Ambil frame tertua dari antrean (Frame "Sekarang" untuk dirender)
                    data = frame_buffer.popleft()
                    curr_frame = data['frame']
                    curr_faces = data['faces_x']

                    # --- LOGIKA LOOK-AHEAD ---
                    # Untuk membuat pergerakan kamera lebih 'cerdas' dan tidak reaktif,
                    # kita 'mengintip' posisi wajah di beberapa frame berikutnya (dari buffer).
                    future_xs = []
                    
                    # Masukkan posisi wajah frame saat ini (jika ada)
                    if curr_faces: future_xs.append(curr_faces[0])
                    
                    # Intip masa depan di buffer
                    for item in frame_buffer:
                        if item['faces_x']:
                            future_xs.append(item['faces_x'][0])
                    
                    if future_xs:
                        # Target kamera adalah RATA-RATA dari posisi wajah sekarang dan di masa depan.
                        avg_target = int(sum(future_xs) / len(future_xs))
                        # Hasil rata-rata ini kemudian dihaluskan lagi dengan LERP untuk inersia.
                        smooth_x = self._get_smooth_x('left', avg_target)
                    else:
                        # Fallback jika tidak ada wajah sama sekali di buffer:
                        # Tetap di posisi terakhir atau kembali ke tengah.
                        smooth_x = self._get_smooth_x('left', self.prev_centers.get('left', w // 2))
                
                    left = np.clip(smooth_x - (target_w // 2), 0, w - target_w)
                    final_frame = curr_frame[0:h, int(left):int(left + target_w)]
                    final_frame = cv2.resize(final_frame, (target_w, h))
                
                    out.write(final_frame)
                
                # Jika stream habis dan buffer kosong, berhenti
                if not ret and not frame_buffer:
                    break
        finally:
            # Reset state untuk pemanggilan berikutnya, memastikan tidak ada sisa data
            # dari pemrosesan klip sebelumnya yang memengaruhi klip berikutnya.
            self.prev_centers = {}
            self.mode_history = []

    def _cinematic_logic(self, cap, out, w_in, h_in, fps):
        """Logika inti untuk Cinematic Mode (Vlog/Doc)."""
        # Tentukan resolusi output (misal: 1080x1920)
        w_out = 1080
        h_out = 1920

        # 2. Hitung dimensi crop dan scale (lakukan sekali saja)
        # Potong sesuai margin yang ditentukan
        crop_margin = self.CINEMATIC_CROP_MARGIN
        crop_x_start = int(w_in * crop_margin)
        crop_x_end = int(w_in * (1 - crop_margin))
        cropped_w = crop_x_end - crop_x_start

        # Skalakan video yang sudah dipotong agar pas dengan lebar output
        scale_factor = w_out / cropped_w
        scaled_h = int(h_in * scale_factor)

        # Hitung posisi vertikal untuk menempatkan video di tengah
        y_offset = (h_out - scaled_h) // 2

        bg_x_start = max(0, (w_in - w_out) // 2)

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: break

                # 1. Buat Background Blur
                bg_crop = frame[:, bg_x_start:bg_x_start+w_out]
                if bg_crop.shape[1] < w_out: # Fallback jika video input kecil
                    bg_crop = cv2.resize(frame, (w_out, h_in))
                
                small_bg = cv2.resize(bg_crop, (0,0), fx=0.1, fy=0.1, interpolation=cv2.INTER_NEAREST)
                blurred_small = cv2.GaussianBlur(small_bg, (9, 9), 0)
                background = cv2.resize(blurred_small, (w_out, h_out), interpolation=cv2.INTER_LINEAR)
                final_frame = cv2.addWeighted(background, 0.6, np.zeros_like(background), 0, 0)

                # 2. Tempel Foreground
                cropped_frame = frame[0:h_in, crop_x_start:crop_x_end]
                scaled_frame = cv2.resize(cropped_frame, (w_out, scaled_h), interpolation=cv2.INTER_AREA)
                
                if y_offset < 0:
                    final_frame = scaled_frame[-y_offset:-y_offset+h_out, :]
                else:
                    final_frame[y_offset : y_offset + scaled_h, 0:w_out] = scaled_frame

                out.write(final_frame)
        except Exception as e:
            logging.error(f"Error dalam _cinematic_logic: {e}")

    def _podcast_logic(self, cap, out, w, h, fps):
        """Logika inti untuk Podcast Mode (Smart Static)."""
        target_w = int(h * 9 / 16)

        # Panggil helper untuk inisialisasi detector jika belum ada.
        if not self.detector: self._initialize_detector()

        # --- STATE VARIABLES ---
        
        # 1. Mode Switching (Hysteresis)
        active_mode = 1  # 1: Single, 2: Split
        mode_buffer = deque(maxlen=self.MODE_BUFFER_SIZE)
        
        # 2. State untuk Single Mode (Smart Static)
        current_camera_x = w // 2  # Posisi awal kamera (tengah)
        stability_counter = 0      
        movement_deadzone_px = w * self.PODCAST_MOVEMENT_DEADZONE_RATIO

        # 3. Split Mode (Layout & Smoothing)
        self.prev_centers = {} # Reset smoothing state
        zoom_factor = self.PODCAST_SPLIT_ZOOM_FACTOR
        split_crop_h = int(h * zoom_factor)
        split_crop_w = int(split_crop_h * (target_w / (h // 2)))
        split_y_start = (h - split_crop_h) // 2
        split_y_end = split_y_start + split_crop_h
        
        frame_count = 0
        last_timestamp_ms = -1

        try:
            # [LOOK-AHEAD SETUP]
            lookahead_range = self.LOOKAHEAD_RANGE
            frame_buffer = deque()

            while True:
                # --- FASE 1: BACA & DETEKSI (Mengisi Buffer) ---
                ret, frame = cap.read()
                
                if ret:
                    # Deteksi Wajah
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    # Hitung timestamp manual dan pastikan selalu naik.
                    timestamp_ms = int((frame_count * 1000) / fps) 
                    if timestamp_ms <= last_timestamp_ms:
                        timestamp_ms = last_timestamp_ms + 1
                    last_timestamp_ms = timestamp_ms

                    result = self.detector.detect_for_video(mp_image, timestamp_ms)
                    # Ambil koordinat wajah
                    faces_x = []
                    if result.detections:
                        for det in result.detections:
                            bbox = det.bounding_box
                            faces_x.append(int(bbox.origin_x + (bbox.width / 2)))
                        faces_x.sort()

                    # --- LOGIKA HYSTERESIS MODE ---
                    detected_mode = 2 if len(faces_x) >= 2 else 1
                    mode_buffer.append(detected_mode)
                    
                    # Cek konsistensi buffer (90% harus sama untuk pindah mode)
                    if mode_buffer.count(2) > int(len(mode_buffer) * self.MODE_SWITCH_THRESHOLD):
                        active_mode = 2
                    elif mode_buffer.count(1) > int(len(mode_buffer) * self.MODE_SWITCH_THRESHOLD):
                        active_mode = 1
                    
                    # Simpan ke buffer
                    frame_buffer.append({
                        'frame': frame,
                        'faces_x': faces_x,
                        'active_mode': active_mode
                    })
                    frame_count += 1

                # --- FASE 2: RENDER BUFFER (Look-Ahead) ---
                if len(frame_buffer) > lookahead_range or (not ret and frame_buffer):
                    data = frame_buffer.popleft()
                    curr_frame = data['frame']
                    curr_faces = data['faces_x']
                    curr_mode = data['active_mode']

                    if curr_mode == 2:
                        # --- MODE 2: SPLIT SCREEN (PODCAST 2 ORANG) ---
                        # Hitung rata-rata posisi wajah masa depan untuk stabilitas maksimal
                        future_lefts = []
                        future_rights = []
                        
                        # Masukkan data saat ini
                        if len(curr_faces) >= 2:
                            future_lefts.append(curr_faces[0])
                            future_rights.append(curr_faces[-1])
                            
                        # Intip masa depan di buffer
                        for item in frame_buffer:
                            if len(item['faces_x']) >= 2:
                                future_lefts.append(item['faces_x'][0])
                                future_rights.append(item['faces_x'][-1])
                        
                        # Hitung target rata-rata (atau fallback ke posisi terakhir)
                        if future_lefts:
                            raw_tx1 = int(sum(future_lefts) / len(future_lefts))
                        else:
                            raw_tx1 = self.prev_centers.get('p_top', w // 4)
                            
                        if future_rights:
                            raw_tx2 = int(sum(future_rights) / len(future_rights))
                        else:
                            raw_tx2 = self.prev_centers.get('p_bottom', w * 3 // 4)
                        
                        # Terapkan Smoothing LERP
                        smooth_tx1 = self._get_smooth_x('p_top', raw_tx1)
                        smooth_tx2 = self._get_smooth_x('p_bottom', raw_tx2)
                        
                        # Crop Top
                        l1 = np.clip(smooth_tx1 - (split_crop_w // 2), 0, w - split_crop_w)
                        top_crop = curr_frame[split_y_start:split_y_end, int(l1):int(l1 + split_crop_w)]
                        top_half = cv2.resize(top_crop, (target_w, h // 2))
                        
                        # Crop Bottom
                        l2 = np.clip(smooth_tx2 - (split_crop_w // 2), 0, w - split_crop_w)
                        bottom_crop = curr_frame[split_y_start:split_y_end, int(l2):int(l2 + split_crop_w)]
                        bottom_half = cv2.resize(bottom_crop, (target_w, h // 2))
                        
                        final_frame = np.vstack((top_half, bottom_half))
                        stability_counter = 0
                    else:
                        # --- MODE 1: SMART STATIC CUT (PODCAST 1 ORANG) ---
                        # Hitung rata-rata posisi wajah masa depan untuk keputusan Cut yang akurat
                        future_targets = []
                        if curr_faces: future_targets.append(curr_faces[0])
                        
                        for item in frame_buffer:
                            if item['faces_x']: future_targets.append(item['faces_x'][0])
                        
                        # Target adalah rata-rata posisi masa depan
                        if future_targets:
                            target_x = int(sum(future_targets) / len(future_targets))
                        else:
                            target_x = current_camera_x

                        # --- LOGIKA SMART STATIC CUT DENGAN DEADZONE ---
                        # Hitung jarak antara posisi kamera saat ini dengan target wajah
                        diff = abs(target_x - current_camera_x)

                        # Jika wajah keluar dari 'deadzone' (berpindah cukup jauh), mulai hitung stabilitas.
                        if diff > movement_deadzone_px:
                            stability_counter += 1
                            # Jika posisi baru konsisten selama >THRESHOLD frame, lakukan 'CUT' (pindah kamera).
                            if stability_counter > self.PODCAST_STABILITY_THRESHOLD:
                                current_camera_x = target_x
                                stability_counter = 0 # Reset counter setelah cut.
                        else:
                            # Jika wajah masih dalam deadzone, reset counter (kamera tetap diam)
                            stability_counter = 0

                        # Lakukan Crop Statis
                        left = np.clip(current_camera_x - (target_w // 2), 0, w - target_w)
                        final_frame = curr_frame[0:h, int(left):int(left + target_w)]
                    
                    out.write(final_frame)
                
                # Jika stream habis dan buffer kosong, berhenti
                if not ret and not frame_buffer:
                    break
        finally:
            # Reset state untuk pemanggilan berikutnya
            self.prev_centers = {}
            self.mode_history = []

    def _process_video_core(self, input_path: str, output_path: str, logic_function, target_resolution_func):
        """
        Template method untuk menangani boilerplate pemrosesan video.
        Membuka, menulis, menutup file, dan menggabungkan audio.
        """
        # Tutup dan reset detector yang ada sebelum memproses klip baru untuk mereset timestamp.
        self.close()

        # Gunakan pathlib untuk manipulasi nama file yang aman
        out_p = Path(output_path)
        temp_output = str(out_p.with_name(f"{out_p.stem}_temp_v{out_p.suffix}"))
        
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logging.error(f"Gagal membuka video: {input_path}")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Dapatkan resolusi target dari fungsi yang diberikan
        target_w, target_h = target_resolution_func(w, h)

        out = cv2.VideoWriter(temp_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (target_w, target_h))

        try:
            # Jalankan logika pemrosesan spesifik (misal: _portrait_logic)
            logic_function(cap, out, w, h, fps)
        except Exception as e:
            logging.error(f"Error selama pemrosesan video '{logic_function.__name__}': {e}", exc_info=True)
            return False
        finally:
            # Pastikan semua resource dilepaskan
            cap.release()
            out.release()

        # Gabungkan audio setelah pemrosesan visual selesai
        return self.add_audio(temp_output, input_path, output_path)

    def process_portrait(self, input_path: str, output_path: str):
        """Memproses video menggunakan logika Monologue Mode."""
        return self._process_video_core(
            input_path,
            output_path,
            self._portrait_logic,
            lambda w, h: (int(h * 9 / 16), h)
        )

    def process_cinematic_portrait(self, input_path: str, output_path: str):
        """Memproses video menggunakan logika Cinematic Mode."""
        return self._process_video_core(
            input_path,
            output_path,
            self._cinematic_logic,
            lambda w, h: (1080, 1920) # Resolusi output tetap
        )

    def process_podcast_portrait(self, input_path: str, output_path: str):
        """Memproses video menggunakan logika Podcast Mode."""
        return self._process_video_core(
            input_path,
            output_path,
            self._podcast_logic,
            lambda w, h: (int(h * 9 / 16), h)
        )

    def add_audio(self, video_visual_path, audio_source_path, final_output_path):
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
            self.ffmpeg_path, '-y',
            '-i', v_path,    # Input 0: Video tanpa suara
            '-i', a_path,    # Input 1: Video asli (sumber audio)
            '-c:v', 'copy',             # Video tidak di-encode ulang (cepat)
            '-c:a', 'copy',             # [FIX] Copy audio stream (jangan re-encode) agar sync terjaga
            '-map', '0:v:0',            # Ambil video dari input 0
            '-map', '1:a:0',            # Ambil audio dari input 1
            '-map_metadata', '-1',      # Hapus metadata lama yang mengganggu
            '-shortest',                # Samakan durasi dengan yang terpendek
            o_path
        ]
        try:
            duration = get_duration(v_path, self.ffprobe_path)
            run_ffmpeg_with_progress(cmd, duration, "   🎵 Menggabungkan audio...")
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