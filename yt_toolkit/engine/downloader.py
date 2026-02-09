import os
import json
import logging
import urllib.request
from typing import Optional, List
import shutil

# Import utilitas umum
from yt_toolkit.core.utils import extract_video_id, sanitize_filename, setup_paths, print_progress, get_common_ffmpeg_args

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
    def __init__(self, url: str, temp_root: str, video_id: Optional[str] = None, cookies_path: Optional[str] = None, progress_callback=None, force_30fps: bool = True):
        self.url = url
        self.temp_root = temp_root
        self.youtube_id = video_id or extract_video_id(url) or 'unknown_video'
        self.cookies_path = cookies_path
        self.progress_callback = progress_callback
        self.force_30fps = force_30fps

        # Properti ini akan diisi oleh setup_directories()
        self.video_title: Optional[str] = None
        self.channel_name: Optional[str] = None
        self.asset_folder_name: Optional[str] = None
        self.summarize_dir: Optional[str] = None
        self.video_dir: Optional[str] = None

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

                if self.progress_callback:
                    # Kirim data mentah ke GUI (0.0 - 1.0) atau (0-100)
                    self.progress_callback(percent, f"{task_name}: {speed_str} (ETA: {eta_str})")
                else:
                    # Visual Bar (Menggunakan karakter block) untuk CLI
                    print_progress(percent, task_name, f"| {eta_str}")
            except Exception:
                pass
                
        elif d['status'] == 'finished':
            print(f"\r✅ {task_name}: Selesai! {' ' * 80}", end='\r', flush=True)

    def setup_directories(self):
        """Mengambil metadata video untuk membuat nama folder yang deskriptif."""
        print("⏳ Metadata...", end='\r', flush=True)
        opts = {'quiet': True, 'no_warnings': True, 'logger': QuietLogger()}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            self.video_title = info.get('title', 'unknown-title')
            self.channel_name = info.get('uploader', 'unknown-channel')
        
        sanitized_title = sanitize_filename(self.video_title)
        sanitized_channel = sanitize_filename(self.channel_name)
        
        # Format: [Channel] [Judul] [ID] (Dipisah spasi)
        self.asset_folder_name = f"{sanitized_channel} {sanitized_title} {self.youtube_id}"
        
        # Setup sub-folder spesifik
        self.summarize_dir = os.path.join(self.temp_root, 'summarize', self.asset_folder_name)
        self.video_dir = os.path.join(self.temp_root, 'video_handling', self.asset_folder_name)
        
        os.makedirs(self.summarize_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
        
        print(f"\r✅ Metadata OK: {self.video_title[:30]}...{' '*20}", end='\r', flush=True)

    def get_clips(self) -> List[dict]:
        """Membaca file transcripts.json dari folder summarize dan mengembalikan daftar klip."""
        if not self.summarize_dir: return []
        
        json_path = os.path.join(self.summarize_dir, 'transcripts.json')
        if not os.path.exists(json_path):
            return []
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('clips', [])
        except Exception as e:
            logging.error(f"Gagal membaca clips dari JSON: {e}")
            return []

    def download_clips_directly(self, clips: List[dict]) -> List[str]:
        """
        Mengunduh potongan klip spesifik langsung dari YouTube (Partial Download).
        Menghemat kuota dan waktu karena tidak perlu mengunduh video full.
        
        Args:
            clips: List dictionary [{'start_time': 10.5, 'end_time': 20.0}, ...]
        """
        if yt_dlp is None:
            logging.error("yt-dlp tidak tersedia atau versi tidak kompatibel.")
            return []

        if not clips:
            return []

        # Folder khusus untuk klip langsung
        direct_clips_dir = os.path.join(self.video_dir, 'raw_clips')
        # Gunakan folder temp untuk memastikan kita menangkap file yang benar
        temp_dl_dir = os.path.join(direct_clips_dir, 'temp_dl')
        os.makedirs(direct_clips_dir, exist_ok=True)
        os.makedirs(temp_dl_dir, exist_ok=True)

        # Konversi format clips (dari JSON transcript) ke format range yt-dlp
        ranges = []
        for c in clips:
            # Dukung berbagai format key (start_time dari JSON atau start umum)
            start = c.get('start_time') or c.get('start')
            end = c.get('end_time') or c.get('end')
            if start is not None and end is not None:
                ranges.append({'start_time': float(start), 'end_time': float(end)})

        if not ranges:
            logging.warning("Tidak ada timestamp valid dalam daftar klip.")
            return []

        print(f"✂️ Mengunduh {len(ranges)} klip...", end='\r', flush=True)

        # Membuat filter range menggunakan lambda, que es el método estándar de yt-dlp.
        # La función lambda recibe el diccionario de información y debe devolver la lista de rangos.
        range_filter = lambda info, ydl: ranges

        # Gunakan format timestamp native dari yt-dlp agar unik dan aman
        outtmpl = 'clip_%(section_start)s-%(section_end)s.%(ext)s'

        # Susun argumen FFmpeg secara dinamis
        ffmpeg_args = get_common_ffmpeg_args() + [
            '-vsync', '1',       # Force CFR
            '-c:a', 'aac',
            '-ar', '44100',
            '-af', 'aresample=async=1:min_comp=0.001:max_soft_comp=0.01',
            '-map_metadata', '-1',
            '-fflags', '+genpts'
        ]

        if self.force_30fps:
            ffmpeg_args.extend(['-r', '30'])

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'logger': QuietLogger(),
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'merge_output_format': 'mkv',
            'paths': {'home': temp_dl_dir}, # Download ke temp dulu
            'outtmpl': outtmpl,
            'download_ranges': range_filter,
            'force_keyframes_at_cuts': True,
            'cookiefile': self.cookies_path,
            'progress_hooks': [lambda d: self._custom_progress_hook(d, "Direct Clip")],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mkv',
            }],
            'postprocessor_args': {
                'FFmpegVideoConvertor': ffmpeg_args,
            },
        }

        downloaded_files = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            
            # Pindahkan file dari temp ke folder tujuan
            for f in os.listdir(temp_dl_dir):
                src_path = os.path.join(temp_dl_dir, f)
                dst_path = os.path.join(direct_clips_dir, f)
                
                if os.path.isfile(src_path) and f.endswith(('.mp4', '.mkv', '.webm')):
                    # Pindahkan (Overwrite jika ada)
                    shutil.move(src_path, dst_path)
                    downloaded_files.append(dst_path)
            
            # Urutkan file (opsional)
            downloaded_files.sort()
            
            # Bersihkan temp
            try: os.rmdir(temp_dl_dir)
            except: pass
            
            print(f"\r✅ {len(downloaded_files)} klip terunduh.{' '*40}")
            return downloaded_files

        except Exception as e:
            logging.error(f"Gagal melakukan direct download clips: {e}")
            return []

    def download_audio_for_ai(self) -> Optional[str]:
        """Mengunduh audio dan langsung mengonversinya ke MP3 untuk AI (Hemat Kuota)."""
        if yt_dlp is None:
            logging.error(f"Library 'yt_dlp' tidak ditemukan.")
            return None

        # 1. Cek apakah file hasil konversi sudah ada
        filename = "audio_for_ai.mp3"
        final_output = os.path.join(self.summarize_dir, filename)
        
        if os.path.exists(final_output):
            # Validasi ukuran file untuk mencegah penggunaan file korup/kosong (misal < 10KB)
            if os.path.getsize(final_output) > 10240:
                logging.info(f"Audio untuk AI sudah tersedia: {filename}")
                return final_output
            else:
                logging.warning(f"File audio ditemukan tapi terlalu kecil/korup. Mengunduh ulang...")
                try: os.remove(final_output)
                except: pass

        # 2. Download Audio & Convert via Postprocessor

        opts = {
            'quiet': True,
            'logger': QuietLogger(),
            'noprogress': True,
            'retries': 10,
            'fragment_retries': 10,
            'retry_sleep': 5,
            'continuedl': True,
            'cookiefile': self.cookies_path,
            'format': 'bestaudio/best',
            'paths': {'home': self.summarize_dir},
            'outtmpl': 'audio_for_ai.%(ext)s',
            'progress_hooks': [lambda d: self._custom_progress_hook(d, "Downloading Audio")],
            'concurrent_fragment_downloads': 5,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            
            if os.path.exists(final_output):
                return final_output
            return None
        except Exception as e:
            logging.error(f"Gagal download audio: {e}")
            return None

def fetch_youtube_transcript(video_url: str, cookies_path: Optional[str] = None, prefer_langs: tuple = ('id', 'en')) -> Optional[str]:
    """Mengambil transkrip video YouTube menggunakan yt-dlp (JSON3)."""
    if yt_dlp is None:
        return None
    
    try:
        print("⏳ Mengambil transkrip (yt-dlp)...", end='\r', flush=True)
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': cookies_path
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            subtitles = info.get('subtitles') or {}
            auto_captions = info.get('automatic_captions') or {}
            all_subs = {**auto_captions, **subtitles}

            target_url = None
            
            for lang in prefer_langs:
                if lang in all_subs:
                    for fmt in all_subs[lang]:
                        if fmt.get('ext') == 'json3':
                            target_url = fmt['url']
                            break
                if target_url: break
            
            if target_url:
                req = urllib.request.Request(
                    target_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                )
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode())
                
                full_text = []
                for event in data.get('events', []):
                    segs = event.get('segs')
                    if segs:
                        text = "".join([s.get('utf8', '') for s in segs]).strip()
                        start_ms = event.get('tStartMs', 0)
                        start_sec = start_ms / 1000.0
                        if text:
                            full_text.append(f"[{start_sec:.2f}] {text}")
                
                return "\n".join(full_text)
    except Exception as e:
        logging.warning(f"Gagal mengambil transkrip via yt-dlp: {e}")
        return None
