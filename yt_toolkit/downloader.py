import os
import json
import logging
import re
import subprocess
from typing import Tuple, Optional, List

# Import utilitas umum
from .utils import get_duration, run_ffmpeg_with_progress

try:
    import yt_dlp
except ImportError as e:
    yt_dlp = None
    _yt_dlp_error = e
else:
    _yt_dlp_error = None

class QuietLogger:
    """Logger kustom untuk membungkam output standar yt-dlp di konsol,
    namun tetap mencatatnya ke file log untuk keperluan debugging."""
    def debug(self, msg): logging.debug(f"[yt-dlp] {msg}")
    def warning(self, msg): logging.info(f"[yt-dlp] {msg}")
    def error(self, msg): logging.error(f"[yt-dlp] {msg}")

class DownloadVidio:
    """
    Class untuk menangani semua proses yang berhubungan dengan download dan manipulasi file video.
    Mencakup:
    - Mengunduh video dan audio dari URL.
    - Mengonversi audio untuk AI.
    - Menggabungkan (remux) video dan audio menjadi file master.
    - Memotong file master menjadi klip-klip pendek.
    """
    def __init__(self, url: str, output_dir: str, ffmpeg_path: str, ffprobe_path: str, deno_path: str, use_gpu: bool = True, video_id: Optional[str] = None, resolution: str = "1080"):
        self.url = url
        self.base_output_dir = output_dir
        self.youtube_id = video_id or self.extract_video_id(url) or 'unknown_video'
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.deno_path = deno_path
        self.use_gpu = False # Dipaksa False (CPU Only) sesuai permintaan
        self.resolution = str(resolution).lower().replace('p', '') # Normalisasi resolusi

        # Properti ini akan diisi oleh setup_directories()
        self.video_title: Optional[str] = None
        self.channel_name: Optional[str] = None
        self.asset_folder_name: Optional[str] = None
        self.raw_dir: Optional[str] = None

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Mengekstrak ID video 11 karakter dari URL YouTube."""
        regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        m = re.search(regex, url)
        return m.group(1) if m else None

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Membersihkan string agar menjadi nama file/folder yang valid."""
        # Hapus karakter ilegal
        name = re.sub(r'[\\/*?:"<>|]', "", name)
        # Pastikan spasi ganda menjadi satu
        name = re.sub(r'\s+', ' ', name).strip()
        # Batasi panjangnya agar tidak terlalu panjang untuk path Windows
        return name[:40]

    def _custom_progress_hook(self, d, task_name):
        """Hook kustom untuk menampilkan progress bar yang lebih bersih."""
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                
                if total:
                    percent = (downloaded / total) * 100
                else:
                    percent = 0
                
                # Format Speed
                speed = d.get('speed')
                if speed:
                    if speed > 1024*1024:
                        speed_str = f"{speed/1024/1024:.2f} MiB/s"
                    else:
                        speed_str = f"{speed/1024:.2f} KiB/s"
                else:
                    speed_str = "N/A"
                
                # Format ETA
                eta = d.get('eta')
                if eta:
                    m, s = divmod(eta, 60)
                    eta_str = f"{int(m)}:{int(s):02d}"
                else:
                    eta_str = "--:--"

                # Visual Bar (Menggunakan karakter block)
                bar_length = 25
                filled_length = int(bar_length * percent // 100)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                # Print dengan \r untuk overwrite baris yang sama
                print(f"\r📥 {task_name}: [{bar}] {percent:.1f}% | 🚀 {speed_str} | ⏳ {eta_str}   ", end='', flush=True)
            except Exception:
                pass
                
        elif d['status'] == 'finished':
            print(f"\r✅ {task_name}: Selesai! {' ' * 50}", flush=True)

    def setup_directories(self):
        """Mengambil metadata video untuk membuat nama folder yang deskriptif."""
        print("⏳ Mengambil metadata video...", end='\r', flush=True)
        # [CLEANUP] Tambahkan logger bisu
        opts = {'quiet': True, 'no_warnings': True, 'logger': QuietLogger()}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            self.video_title = info.get('title', 'unknown-title')
            self.channel_name = info.get('uploader', 'unknown-channel')
        
        sanitized_title = self._sanitize_filename(self.video_title)
        sanitized_channel = self._sanitize_filename(self.channel_name)
        
        # Format: [Channel] [Judul] [ID] (Dipisah spasi)
        self.asset_folder_name = f"{sanitized_channel} {sanitized_title} {self.youtube_id}"
        self.raw_dir = os.path.join(self.base_output_dir, self.asset_folder_name)
        os.makedirs(self.raw_dir, exist_ok=True)
        print(f"\r✅ Metadata didapatkan: {self.video_title[:40]}...{' '*20}", flush=True)

    def download_both_separate(self) -> Tuple[Optional[str], Optional[str]]:
        """Mengunduh video dan audio secara terpisah dengan format asli."""
        if yt_dlp is None:
            logging.error(f"Library 'yt_dlp' tidak ditemukan atau gagal dimuat. Detail: {_yt_dlp_error}")
            return None, None
            
        video_tmpl = os.path.join(self.raw_dir, 'vidio.%(ext)s')
        audio_tmpl = os.path.join(self.raw_dir, 'audio.%(ext)s')

        try:
            video_opts = {
                'format': f'bestvideo[height<={self.resolution}]/best[height<={self.resolution}]',
                'outtmpl': video_tmpl,
                'quiet': True,      # Sembunyikan output log yt-dlp
                'logger': QuietLogger(), # [CLEANUP] Gunakan logger bisu
                'noprogress': True, # Sembunyikan progress bar bawaan
                'progress_hooks': [lambda d: self._custom_progress_hook(d, "Video")],
                'retries': 10,
                'fragment_retries': 10,
                'retry_sleep': 5,
                'continuedl': True,
                'remote_components': ['ejs:github', 'ejs:npm'], 
                'update_remote_components': True,            
                'js_runtimes': {
                    'deno': {
                        'path': self.deno_path
                    }
                },
                'postprocessor_args': [
                '-map_metadata', '-1',
                ],
                
            }

            # 2. Konfigurasi Download Audio (Default / Raw)
            audio_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_tmpl,
                'quiet': True,
                'logger': QuietLogger(), # [CLEANUP] Gunakan logger bisu
                'noprogress': True,
                'progress_hooks': [lambda d: self._custom_progress_hook(d, "Audio")],
                'retries': 10,
                'fragment_retries': 10,
                'retry_sleep': 5,
                'continuedl': True,
                'remote_components': ['ejs:github', 'ejs:npm'], 
                'update_remote_components': True,            
                'js_runtimes': {
                    'deno': {
                        'path': self.deno_path
                    }
                },
            }
            # Download Video
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                v_info = ydl.extract_info(self.url, download=True)
                v_path = v_info.get('filepath') or ydl.prepare_filename(v_info)

            # Download Audio
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                a_info = ydl.extract_info(self.url, download=True)
                a_path = a_info.get('filepath') or ydl.prepare_filename(a_info)

            return v_path, a_path
        except Exception as e:
            logging.error(f"Gagal download: {e}")
            return None, None

    def convert_audio_for_ai(self, input_audio_path: str) -> Optional[str]:
        """Mengonversi audio ke MP3 standar untuk kompatibilitas AI (Gemini)."""
        if not input_audio_path or not os.path.exists(input_audio_path):
            logging.error("Input audio tidak ditemukan untuk konversi AI.")
            return None

        output_path = os.path.join(self.raw_dir, "audio_for_ai.mp3")
        
        if os.path.exists(output_path):
            logging.info(f"Audio untuk AI sudah tersedia: {os.path.basename(output_path)}")
            return output_path

        print("⏳ Mengonversi audio ke MP3 untuk AI...", end='\r', flush=True)
        
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', input_audio_path,
            '-vn',              # Pastikan tidak ada video stream
            '-ar', '44100',     # Sample rate standar
            '-ac', '2',         # Stereo
            '-b:a', '128k',     # Bitrate 128k (cukup untuk speech-to-text)
            output_path
        ]
        
        try:
            duration = get_duration(input_audio_path, self.ffprobe_path)
            run_ffmpeg_with_progress(cmd, duration, "Converting Audio for AI")
            return output_path
        except subprocess.CalledProcessError:
            logging.error("Gagal mengonversi audio untuk AI.")
            return None

    def remux_video_audio(self, video_path: str, audio_path: str) -> Optional[str]:
        """Menggabungkan video dan audio ke master.mkv (Re-encode untuk Standarisasi)."""
        if not video_path or not audio_path:
            logging.error("Path video atau audio tidak ditemukan (None). Remux dibatalkan.")
            return None

        output_path = os.path.join(self.raw_dir, 'master.mkv')
        
        if os.path.exists(output_path):
            logging.info(f"File master sudah ada: {output_path}")
            return output_path
        
        # --- Konfigurasi FFmpeg untuk CPU (libx264) ---
        # Konfigurasi CPU (libx264)
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'libx264',      # Encoder video CPU yang sangat kompatibel.
            '-preset', 'ultrafast', # Preset tercepat, karena kualitas diatur oleh CRF.
            '-crf', '18',           # Constant Rate Factor: Kualitas visual (semakin rendah, semakin bagus). 18 adalah kualitas tinggi.
            '-r', '30',             # Standarisasi frame rate ke 30fps.
            '-g', '30',             # WAJIB: Keyframe tiap 1 detik agar cutting 'copy' akurat
            '-c:a', 'aac',
            '-ar', '44100',
            '-af', 'aresample=async=1:min_comp=0.001:max_soft_comp=0.01',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-fflags', '+genpts',
            '-avoid_negative_ts', 'make_zero',
            output_path
        ]
        duration = get_duration(video_path, self.ffprobe_path)

        try:
            run_ffmpeg_with_progress(cmd, duration, "Remuxing (CPU)")
            return self.fix_metadata(output_path)
        except subprocess.CalledProcessError as e:
            logging.error(f"Gagal remux: {e}")
            return None

    def fix_metadata(self, input_path: str) -> Optional[str]:
        """Memperbaiki timestamp agar sinkron saat dipotong."""
        temp_output = input_path.replace(".mkv", "_fixed.mkv")
        cmd = [self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-i', input_path, 
            '-c', 'copy', 
            temp_output]
        try:
            subprocess.run(cmd, check=True)
            os.replace(temp_output, input_path)
            return input_path
        except:
            return input_path

    def create_raw_clips(self, transcript_json_path: str) -> List[str]:
        """
        Memotong master.mkv menjadi klip-klip kecil berdasarkan JSON.
        Hasilnya adalah klip mentah (Visual + Audio) sebelum diproses AI.
        """

        if not os.path.exists(transcript_json_path):
            logging.error(f"File JSON tidak ditemukan: {transcript_json_path}")
            return []

        with open(transcript_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        clips_metadata = data.get('clips', [])
        master_path = os.path.join(self.raw_dir, 'master.mkv')
        
        if not os.path.exists(master_path):
            logging.error("File master.mkv tidak ditemukan. Lakukan remux terlebih dahulu.")
            return []

        # Folder hasil potongan
        clips_dir = os.path.join(self.raw_dir, 'raw_clip_landscape')
        os.makedirs(clips_dir, exist_ok=True)

        created_files = []

        for i, clip in enumerate(clips_metadata):
            start_sec = (clip['start_time'])
            end_sec = (clip['end_time'])
                
            duration = (end_sec - start_sec)
                
            if duration <= 0:
                continue

            output_clip = os.path.join(clips_dir, f"clip_{i+1}.mkv")

            if os.path.exists(output_clip):
                logging.info(f"⏩ Klip sudah ada: {os.path.basename(output_clip)}")
                created_files.append(output_clip)
                continue

            # CPU Only (libx264)
            cmd = [
                self.ffmpeg_path, '-y',
                '-ss', str(start_sec), 
                '-i', master_path,
                '-t', str(duration),
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', # Re-encode dengan CPU, kualitas baik (23).
                '-c:a', 'aac',          # Re-encode audio ke AAC standar.
                '-b:a', '128k',         # Bitrate audio yang cukup untuk klip pendek.
                '-map_metadata', '-1',  # Hapus semua metadata dari file asli.
                output_clip
            ]

            try:
                run_ffmpeg_with_progress(cmd, duration, f"   ⏳ Memotong klip ({i+1}/{len(clips_metadata)})...")
                created_files.append(output_clip)
            except subprocess.CalledProcessError:
                logging.error(f"Gagal memotong klip {i+1}.")

        return created_files