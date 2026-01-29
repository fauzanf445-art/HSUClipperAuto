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
from contextlib import contextmanager

# Import utilitas umum
from .utils import get_duration, run_ffmpeg_with_progress

@contextmanager
def suppress_stderr():
    """
    Context manager untuk membungkam output stderr (C++ logs) sementara.
    Berguna untuk menyembunyikan log inisialisasi TensorFlow/MediaPipe.
    """
    try:
        # Simpan file descriptor stderr asli
        original_stderr_fd = sys.stderr.fileno()
        
        # Buat null device
        with open(os.devnull, 'w') as devnull:
            # Duplikasi stderr asli agar bisa dikembalikan nanti
            saved_stderr_fd = os.dup(original_stderr_fd)
            
            try:
                # Redirect stderr ke null
                os.dup2(devnull.fileno(), original_stderr_fd)
                yield
            finally:
                # Kembalikan stderr ke aslinya
                os.dup2(saved_stderr_fd, original_stderr_fd)
                os.close(saved_stderr_fd)
    except Exception:
        # Fallback jika terjadi error (misal tidak ada akses ke fileno)
        yield

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
        self.MODE_BUFFER_SIZE = 45         # Jumlah frame untuk validasi perpindahan mode (1.5 detik @ 30fps).
        self.MODE_SWITCH_THRESHOLD = 0.9   # 90% frame di buffer harus konsisten untuk ganti mode.

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

    def process_portrait(self, input_path: str, output_path: str):
        # 1. Tentukan file sementara (tanpa suara)
        temp_output = output_path.replace(".mkv", "_temp_v.mkv")

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened(): 
            logging.error(f"Gagal membuka video: {input_path}")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0 # Fallback jika FPS tidak terdeteksi

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        target_w = int(h * 9 / 16)
        
        out = cv2.VideoWriter(temp_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (target_w, h))

        self.prev_centers = {}
        self.mode_history = [] # Reset buffer untuk video baru
        self.current_mode = 1  # Reset mode ke default
        frame_count = 0 

        # Panggil helper untuk inisialisasi detector dengan fallback GPU->CPU.
        self._initialize_detector()

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
                    
                    # Jalankan Deteksi (Timestamp berdasarkan frame input)
                    result = self.detector.detect_for_video(mp_image, int((frame_count * 1000) / fps))

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

                    # Tentukan mode berdasarkan history input saat ini
                    mode = self._determine_mode(len(faces_x))
                    
                    # Simpan ke buffer
                    frame_buffer.append({
                        'frame': frame,
                        'faces_x': faces_x,
                        'mode': mode
                    })
                    frame_count += 1
                
                # 2. FASE RENDER (Hanya jika buffer penuh atau stream habis)
                # Kita butuh buffer terisi minimal 'lookahead_range' sebelum mulai render
                if len(frame_buffer) > lookahead_range or (not ret and frame_buffer):
                    
                    # Ambil frame tertua dari antrean (Frame "Sekarang" untuk dirender)
                    data = frame_buffer.popleft()
                    curr_frame = data['frame']
                    curr_faces = data['faces_x']
                    curr_mode = data['mode']
                    
                    if curr_mode == 2:
                    # --- MODE 2: CINEMATIC (ZOOM + BLUR BACKGROUND) ---
                    
                    # 1. Buat Background Blur (Optimized)
                    # Ambil bagian tengah frame selebar target_w untuk background
                        bg_x_start = max(0, (w - target_w) // 2)
                        bg_crop = curr_frame[:, bg_x_start:bg_x_start+target_w]
                    
                    # Teknik Cepat: Downscale -> Blur -> Upscale (Hemat CPU)
                        small_bg = cv2.resize(bg_crop, (0,0), fx=0.1, fy=0.1, interpolation=cv2.INTER_NEAREST)
                        blurred_small = cv2.GaussianBlur(small_bg, (9, 9), 0)
                        background = cv2.resize(blurred_small, (target_w, h), interpolation=cv2.INTER_LINEAR)
                    # Gelapkan background agar video utama lebih menonjol (Dimming)
                        final_frame = cv2.addWeighted(background, 0.6, np.zeros_like(background), 0, 0)

                    # 2. Siapkan Foreground (Video Utama)
                    # Potong 15% kiri dan kanan (Zoom) agar video lebih memenuhi layar
                        crop_margin = self.CINEMATIC_CROP_MARGIN 
                        x_start = int(w * crop_margin)
                        x_end = int(w * (1 - crop_margin))
                        fg_crop = curr_frame[:, x_start:x_end]
                    
                    # Resize foreground agar lebarnya pas dengan target_w
                        fg_h_new = int(target_w * (h / (x_end - x_start)))
                        foreground = cv2.resize(fg_crop, (target_w, fg_h_new), interpolation=cv2.INTER_AREA)
                    
                    # 3. Tempel Foreground ke Background
                        y_offset = (h - fg_h_new) // 2
                    
                    # Handling jika hasil zoom lebih tinggi dari layar (jarang terjadi dengan margin 0.15)
                        if y_offset < 0:
                            final_frame = foreground[-y_offset:-y_offset+h, :]
                        else:
                            final_frame[y_offset : y_offset + fg_h_new, :] = foreground
                    else:
                    # --- MODE 1: SINGLE FACE TRACKING (MONOLOGUE) ---
                        # --- LOGIKA LOOK-AHEAD ---
                        # Untuk membuat pergerakan kamera lebih 'cerdas' dan tidak reaktif,
                        # kita 'mengintip' posisi wajah di beberapa frame berikutnya (dari buffer).
                        future_xs = []
                        
                        # Masukkan posisi wajah frame saat ini (jika ada)
                        if curr_faces: future_xs.append(curr_faces[0])
                        
                        # Intip masa depan di buffer
                        for item in frame_buffer:
                            if item['mode'] == 1 and item['faces_x']:
                                future_xs.append(item['faces_x'][0])
                        
                        if future_xs:
                            # Target kamera adalah RATA-RATA dari posisi wajah sekarang dan di masa depan.
                            avg_target = int(sum(future_xs) / len(future_xs))
                            # Hasil rata-rata ini kemudian dihaluskan lagi dengan LERP untuk inersia.
                            smooth_x = self._get_smooth_x('left', avg_target)
                        else:
                            # Fallback jika tidak ada wajah sama sekali di buffer
                            smooth_x = self._get_smooth_x('left', self.prev_centers.get('left', w // 2))
                    
                        left = np.clip(smooth_x - (target_w // 2), 0, w - target_w)
                        final_frame = curr_frame[0:h, int(left):int(left + target_w)]
                        final_frame = cv2.resize(final_frame, (target_w, h))
                
                    out.write(final_frame)
                
                # Jika stream habis dan buffer kosong, berhenti
                if not ret and not frame_buffer:
                    break

        finally:
            # Pastikan resource OpenCV dilepas sebelum masuk ke proses audio
            cap.release()
            out.release()
            # Tutup detector segera setelah selesai satu video
            if self.detector:
                self.detector.close()
                self.detector = None

        # 2. PROSES PENTING: Gabungkan Audio menggunakan FFmpeg
        return self.add_audio(temp_output, input_path, output_path)

    def process_cinematic_portrait(self, input_path: str, output_path: str):
        """
        Mengubah video landscape menjadi portrait dengan menambahkan bar hitam (letterbox).
        Video akan dipotong sedikit di bagian tepi dan ditempatkan di tengah.
        """
        # 1. Setup video capture dan writer
        temp_output = output_path.replace(".mkv", "_temp_v.mkv")
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            logging.error(f"Gagal membuka video: {input_path}")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0

        w_in = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h_in = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Tentukan resolusi output (misal: 1080x1920)
        w_out = 1080
        h_out = 1920

        out = cv2.VideoWriter(temp_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w_out, h_out))

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

        # Koordinat crop untuk background (Center Crop)
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
        finally:
            cap.release()
            out.release()

        # 4. Gabungkan kembali audio
        return self.add_audio(temp_output, input_path, output_path)

    def process_podcast_portrait(self, input_path: str, output_path: str):
        """
        Mode khusus Podcast:
        - Menganalisa wajah untuk menentukan area crop.
        - TIDAK menggunakan motion tracking (panning).
        - Kamera statis (dikunci) dan hanya berpindah (cut) jika posisi subjek berubah drastis.
        """
        temp_output = output_path.replace(".mkv", "_temp_v.mkv")
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened(): return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        target_w = int(h * 9 / 16)
        
        out = cv2.VideoWriter(temp_output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (target_w, h))

        # Panggil helper untuk inisialisasi detector dengan fallback GPU->CPU.
        self._initialize_detector()

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
                    result = self.detector.detect_for_video(mp_image, int((frame_count * 1000) / fps))

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
            cap.release()
            out.release()
            if self.detector: self.detector.close(); self.detector = None

        return self.add_audio(temp_output, input_path, output_path)

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
            '-c:a', 'aac',              # Encode audio ke format AAC agar kompatibel
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