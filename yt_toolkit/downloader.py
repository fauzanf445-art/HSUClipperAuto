import os
import json
import logging
import re
import subprocess
from typing import Tuple, Optional, List

try:
    import yt_dlp
except ImportError as e:
    yt_dlp = None
    _yt_dlp_error = e
else:
    _yt_dlp_error = None

# [CLEANUP] Logger kustom untuk membungkam output yt-dlp sepenuhnya
class QuietLogger:
    # Log debug masuk ke file log (level DEBUG)
    def debug(self, msg): logging.debug(f"[yt-dlp] {msg}")
    # Log warning masuk ke file log (level INFO) agar tidak muncul di terminal (karena terminal filter WARNING)
    def warning(self, msg): logging.info(f"[yt-dlp] {msg}")
    def error(self, msg): logging.error(f"[yt-dlp] {msg}")

class DownloadVidio:
    def __init__(self, url: str, output_dir: str, ffmpeg_path: str, ffprobe_path: str, deno_path: str, use_gpu: bool = True, video_id: Optional[str] = None, resolution: str = "1080"):
        self.url = url
        self.base_output_dir = output_dir
        self.youtube_id = video_id or self.extract_video_id(url) or 'unknown_video'
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.deno_path = deno_path
        self.use_gpu = use_gpu
        self.resolution = str(resolution).lower().replace('p', '')

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

    def _get_duration(self, file_path: str) -> float:
        """Mendapatkan durasi file media dalam detik untuk perhitungan progres."""
        cmd = [
            self.ffprobe_path, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        try:
            return float(subprocess.check_output(cmd).decode('utf-8').strip())
        except Exception:
            return 0.0

    def _run_ffmpeg_with_progress(self, cmd: List[str], total_duration: float, task_name: str):
        """Menjalankan perintah FFmpeg dan menampilkan progress bar."""
        if total_duration <= 0:
            # Fallback ke mode senyap jika durasi tidak diketahui
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return

        # Hapus flag yang berisik
        cmd = [arg for arg in cmd if arg not in ['-stats']]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True, encoding='utf-8', errors='ignore')

        stderr_output = []
        for line in process.stderr:
            stderr_output.append(line)
            if 'time=' in line:
                match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
                if match:
                    hours, minutes, seconds, hundredths = map(int, match.groups())
                    current_time = hours * 3600 + minutes * 60 + seconds + hundredths / 100
                    percent = min(100, int((current_time / total_duration) * 100))
                    bar = '█' * (percent // 2)
                    spaces = ' ' * (50 - (percent // 2))
                    print(f"\r{task_name}: [{bar}{spaces}] {percent}%", end='', flush=True)

        process.wait()
        print('\r', end='', flush=True) # Reset kursor ke awal baris
        if process.returncode != 0:
            # Tampilkan 20 baris terakhir dari error log FFmpeg untuk debugging
            error_log = "".join(stderr_output[-20:])
            logging.error(f"FFmpeg Error Details:\n{error_log}")
            raise subprocess.CalledProcessError(process.returncode, cmd)

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
            duration = self._get_duration(input_audio_path)
            self._run_ffmpeg_with_progress(cmd, duration, "Converting Audio for AI")
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

        def run_remux(gpu_mode):
            # Tentukan parameter encoder berdasarkan mode
            if gpu_mode:
                v_codec, preset = 'h264_nvenc', 'p4'
                # NVENC menggunakan -cq (Constant Quality) atau -qp
                # Menggunakan -rc constqp agar bitrate menyesuaikan kualitas
                quality_args = ['-rc', 'constqp', '-qp', '20']
            else:
                v_codec, preset = 'libx264', 'ultrafast'
                # CPU (libx264) menggunakan -crf
                quality_args = ['-crf', '18']
            
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', v_codec,
                '-preset', preset,
                *quality_args,          # Unpack argumen kualitas di sini
                '-r', '30',             # Mengunci frame rate ke 30fps
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
            duration = self._get_duration(video_path)
            self._run_ffmpeg_with_progress(cmd, duration, "Remuxing")

        try:
            run_remux(self.use_gpu) # Coba dengan GPU
            return self.fix_metadata(output_path)
        except subprocess.CalledProcessError as e:
            if self.use_gpu:
                logging.warning(f"⚠️ Remux GPU gagal. Fallback ke CPU... ({e})")
                try:
                    run_remux(False)
                    return self.fix_metadata(output_path)
                except subprocess.CalledProcessError as cpu_e:
                    logging.error(f"Remux CPU juga gagal setelah fallback.")
            # Jika use_gpu False, error akan langsung tertangkap di sini
            logging.error(f"Gagal remux total. Periksa log FFmpeg di atas untuk detail.")
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

            def run_clip(gpu_mode):
                # [FIX SYNC] UBAH DARI COPY KE RE-ENCODE
                # Stream copy (-c:v copy) menyebabkan desync karena hanya bisa potong di Keyframe.
                # Re-encode menjamin potongan akurat (frame-perfect).
                
                if gpu_mode:
                    # NVENC (Cepat)
                    enc_opts = ['-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'constqp', '-qp', '23']
                else:
                    # CPU (Kompatibel)
                    enc_opts = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23']

                cmd = [
                    self.ffmpeg_path, '-y',
                    '-ss', str(start_sec), 
                    '-i', master_path,
                    '-t', str(duration),
                    *enc_opts,
                    '-c:a', 'aac',  # Audio tetap re-encode ringan agar bisa di-fade
                    '-b:a', '128k',
                    '-map_metadata', '-1',
                    output_clip
                ]
                self._run_ffmpeg_with_progress(cmd, duration, f"   ⏳ Memotong klip ({i+1}/{len(clips_metadata)})...")

            try:
                # Gunakan GPU jika tersedia untuk mempercepat re-encode
                run_clip(self.use_gpu)
                created_files.append(output_clip)
            except subprocess.CalledProcessError:
                # Fallback ke CPU jika GPU gagal
                if self.use_gpu:
                    try:
                        logging.warning(f"   ⚠️ Gagal potong dengan GPU, mencoba CPU...")
                        run_clip(False)
                        created_files.append(output_clip)
                    except:
                        logging.error(f"Gagal memotong klip {i+1}.")
                else:
                    logging.error(f"Gagal memotong klip {i+1}.")

        return created_files