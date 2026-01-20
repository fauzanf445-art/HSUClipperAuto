import cv2
import mediapipe as mp
import os
import logging
import numpy as np
import subprocess
from pathlib import Path
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class VideoProcessor:
    def __init__(self, model_path='detector.tflite', ffmpeg_path='ffmpeg', use_gpu=False):
        """
        Inisialisasi Face Tracker menggunakan MediaPipe Tasks API.
        """
        # Pastikan model .tflite ada di root folder proyek Anda
        if not os.path.exists(model_path):
            logging.error(f"Model {model_path} tidak ditemukan!")
            raise FileNotFoundError(f"Silakan unduh detector.tflite dari MediaPipe.")
            
        self.model_path = model_path
        self.ffmpeg_path = ffmpeg_path
        self.use_gpu = use_gpu
        self.detector = None
        
        # Variabel untuk Smoothing (Peredaman)
        self.prev_left = None
        self.smooth_factor = 0.1 # Semakin kecil semakin halus/lambat gerakannya

    def get_portrait_coordinates(self, frame_width, frame_height, detection):
        """
        Menghitung koordinat crop 9:16 dengan tambahan logika Smoothing.
        """
        target_w = int(frame_height * 9 / 16)
        
        # Ambil pusat wajah dari bounding box
        bbox = detection.bounding_box
        face_center_x = int(bbox.origin_x + (bbox.width / 2))
        
        # Tentukan posisi ideal (wajah di tengah)
        target_left = face_center_x - (target_w // 2)
        
        # Logika Smoothing: Mencegah kamera bergoyang drastis
        if self.prev_left is None:
            self.prev_left = target_left
        else:
            # Linear Interpolation (Lerp)
            self.prev_left = int((1 - self.smooth_factor) * self.prev_left + self.smooth_factor * target_left)
            
        left = self.prev_left

        # Pastikan tidak keluar dari frame asli
        if left < 0:
            left = 0
        elif left + target_w > frame_width:
            left = frame_width - target_w
            
        return left, left + target_w

    def process_portrait(self, input_path: str, output_path: str):
        # 1. Tentukan file sementara (tanpa suara)
        temp_output = output_path.replace(".mkv", "temp_visual.mkv")

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened(): 
            logging.error(f"Gagal membuka video: {input_path}")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 30.0 # Fallback jika FPS tidak terdeteksi

        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        target_w = int(h * 9 / 16)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_output, fourcc, fps, (target_w, h))

        self.prev_left = None
        frame_count = 0 

        # Inisialisasi Detector BARU untuk setiap video (Reset Timestamp)
        # Tentukan Delegate (CPU atau GPU)
        if self.use_gpu:
            delegate = python.BaseOptions.Delegate.GPU
        else:
            delegate = python.BaseOptions.Delegate.CPU
            
        base_options = python.BaseOptions(model_asset_path=self.model_path, delegate=delegate)
        options = vision.FaceDetectorOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO
        )
        self.detector = vision.FaceDetector.create_from_options(options)

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret: break 

                # Inisialisasi koordinat default (tengah)
                left, right = (w // 2 - target_w // 2), (w // 2 + target_w // 2)

                # Konversi untuk MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                timestamp_ms = int((frame_count * 1000) / fps)
                
                # Jalankan Deteksi
                result = self.detector.detect_for_video(mp_image, timestamp_ms)

                # Update koordinat jika wajah ditemukan
                if result and result.detections:
                    left, right = self.get_portrait_coordinates(w, h, result.detections[0])

                # Eksekusi Crop
                portrait_frame = frame[0:h, left:right]
                portrait_frame = cv2.resize(portrait_frame, (target_w, h))
                
                out.write(portrait_frame)
                frame_count += 1
        finally:
            # Pastikan resource OpenCV dilepas sebelum masuk ke proses audio
            cap.release()
            out.release()
            # Tutup detector segera setelah selesai satu video
            if self.detector:
                self.detector.close()
                self.detector = None

        # 2. PROSES PENTING: Gabungkan Audio menggunakan FFmpeg
        print(f"🎵 Menggabungkan audio asli ke: {os.path.basename(output_path)}")
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
            '-loglevel', 'error',
            '-stats',
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
            subprocess.run(cmd, check=True)
            # Hapus file sementara yang tanpa suara jika berhasil
            if os.path.exists(v_path):
                os.remove(v_path)
            return True
        except Exception as e:
            print(f"❌ Gagal menggabungkan audio: {e}")
            return False

    def close(self):
        if self.detector:
            self.detector.close()
            self.detector = None