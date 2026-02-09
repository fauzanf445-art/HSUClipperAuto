import subprocess
import re
import logging
import sys
import os
import shutil
from typing import List, Optional, Tuple
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
from functools import lru_cache
from collections import deque
import time

@contextmanager
def suppress_stderr():
    """Context manager untuk membungkam output stderr (C++ logs) sementara."""
    try:
        original_stderr_fd = sys.stderr.fileno()
        with open(os.devnull, 'w') as devnull:
            saved_stderr_fd = os.dup(original_stderr_fd)
            try:
                os.dup2(devnull.fileno(), original_stderr_fd)
                yield
            finally:
                os.dup2(saved_stderr_fd, original_stderr_fd)
                os.close(saved_stderr_fd)
    except Exception:
        yield

@lru_cache(maxsize=128)
def get_duration(file_path: str) -> float:
    """Mendapatkan durasi file media dalam detik untuk perhitungan progres."""
    cmd = [
        "ffprobe", '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        return float(subprocess.check_output(cmd).decode('utf-8').strip())
    except Exception as e:
        logging.warning(f"Gagal mendapatkan durasi untuk {file_path}: {e}")
        return 0.0

@lru_cache(maxsize=128)
def get_video_resolution(video_path: str) -> Tuple[int, int]:
    """Mendapatkan resolusi asli video (lebar, tinggi) menggunakan ffprobe."""
    cmd = [
        "ffprobe", '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
        video_path
    ]
    try:
        result = subprocess.check_output(cmd).decode('utf-8').strip().split('x')
        return int(result[0]), int(result[1])
    except Exception as e:
        logging.warning(f"Gagal mendapatkan resolusi untuk {video_path}: {e}")
        return 1920, 1080 # Fallback ke resolusi standar

def is_tool_available(tool_path: str) -> bool:
    """Memeriksa apakah sebuah tool (seperti ffmpeg) dapat dieksekusi."""
    try:
        # Menjalankan perintah version, menyembunyikan output
        subprocess.run([tool_path, "-version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def extract_video_id(url: str) -> Optional[str]:
    """Mengekstrak ID video 11 karakter dari URL YouTube."""
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    m = re.search(regex, url)
    return m.group(1) if m else None

def sanitize_filename(name: str) -> str:
    """Membersihkan string agar menjadi nama file/folder yang valid."""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:40]

@lru_cache(maxsize=1)
def get_hw_encoder_args() -> List[str]:
    """
    Mendeteksi encoder hardware terbaik yang tersedia (NVENC/QSV).
    Mengembalikan argumen FFmpeg yang sesuai untuk performa maksimal.
    """
    # 1. Cek NVIDIA NVENC
    try:
        # Mencoba encode dummy frame untuk memastikan NVENC berfungsi
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
             '-c:v', 'h264_nvenc', '-f', 'null', '-'], 
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        logging.info("🚀 Hardware Acceleration: NVIDIA NVENC terdeteksi.")
        return [
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',      # Preset P4 (Medium) - Balance speed/quality
            '-cq', '23',          # Constant Quality (mirip CRF)
            '-rc', 'vbr',
            '-pix_fmt', 'yuv420p'
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 2. Cek Intel QSV
    try:
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
             '-c:v', 'h264_qsv', '-f', 'null', '-'], 
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        logging.info("🚀 Hardware Acceleration: Intel QSV terdeteksi.")
        return [
            '-c:v', 'h264_qsv',
            '-preset', 'veryfast',
            '-global_quality', '23',
            '-look_ahead', '0'
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Fallback CPU (Default Lama)
    return [
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '20',
    ]

def get_common_ffmpeg_args() -> List[str]:
    """Wrapper untuk mendapatkan argumen encoder (cached)."""
    return get_hw_encoder_args()

def print_progress(percent: float, task_name: str, extra_info: str = ""):
    """
    Menampilkan progress bar standar ke terminal.
    Menggantikan print manual yang tersebar di berbagai modul.
    """
    bar_length = 25
    filled_length = int(bar_length * percent // 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    # Batasi panjang extra_info agar tidak merusak tampilan baris
    if len(extra_info) > 30:
        extra_info = extra_info[:27] + "..."
        
    print(f"\r⏳ {task_name}: {bar} {int(percent)}% {extra_info}{' '*10}", end='', flush=True)

def run_ffmpeg_with_progress(cmd: List[str], total_duration: float, task_name: str, progress_callback=None):
    """Menjalankan perintah FFmpeg dan menampilkan progress bar."""
    executable = cmd[0]
    if shutil.which(executable) is None and not os.path.isfile(executable):
        error_msg = f"❌ Program '{executable}' tidak ditemukan. Pastikan FFmpeg sudah terinstal dan ada di PATH."
        logging.critical(error_msg)
        raise FileNotFoundError(error_msg)

    if total_duration <= 0:
        # Fallback ke mode senyap jika durasi tidak diketahui
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise FileNotFoundError(f"❌ FFmpeg tidak ditemukan saat mencoba menjalankan: {cmd[0]}")
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg command failed (duration=0). Command: {' '.join(e.cmd)}. Error: {e.stderr}")
            raise
        return

    cmd = [arg for arg in cmd if arg not in ['-stats']]

    try:
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='ignore')
    except FileNotFoundError:
        raise FileNotFoundError(f"❌ FFmpeg tidak ditemukan saat mencoba menjalankan: {cmd[0]}")

    stderr_output = deque(maxlen=20)
    for line in process.stderr:
        stderr_output.append(line)
        if 'time=' in line:
            match = re.search(r'time=(\d+):(\d{2}):(\d{2})\.(\d{2})', line)
            if match:
                hours, minutes, seconds, hundredths = map(int, match.groups())
                current_time = hours * 3600 + minutes * 60 + seconds + hundredths / 100
                percent = min(100, int((current_time / total_duration) * 100))
                
                if progress_callback:
                    progress_callback(percent, task_name)
                else:
                    bar = '█' * (percent // 2)
                    spaces = ' ' * (50 - (percent // 2))
                    print(f"\r{task_name}: {percent}%{' '*20}", end='', flush=True)

    process.wait()
    if not progress_callback: print('\r', end='', flush=True)
    if process.returncode != 0:
        error_log = "".join(stderr_output)
        logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
        raise subprocess.CalledProcessError(process.returncode, cmd, stderr="".join(stderr_output))

class FFmpegPipeWriter:
    """Wrapper untuk menulis frame raw video ke stdin FFmpeg pipe."""
    def __init__(self, command):
        # Membuka pipe ke FFmpeg
        # [OPTIMASI I/O] Buffer 64MB untuk throughput video HD yang lebih lancar
        self.process = subprocess.Popen(
            command, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            bufsize=64 * 1024 * 1024
        )
    
    def write(self, frame):
        if self.process and self.process.stdin:
            try: 
                # Tulis langsung buffer numpy (hindari copy .tobytes() jika memungkinkan)
                self.process.stdin.write(frame)
            except TypeError:
                # Fallback jika buffer protocol gagal (misal non-contiguous array)
                try: self.process.stdin.write(frame.tobytes())
                except Exception: pass
            except Exception: pass
    
    def release(self):
        if self.process:
            if self.process.stdin: self.process.stdin.close()
            self.process.wait()
            self.process = None

def update_cookies_from_browser(browser_name: str, output_path: str) -> bool:
    """
    Mengekstrak cookies dari browser dan menyimpannya ke file.
    Membutuhkan browser untuk ditutup (terkadang) agar database tidak terkunci.
    """
    print(f"⏳ Mengekstrak cookies dari {browser_name} ke {os.path.basename(output_path)}...", end='\r', flush=True)
    
    try:
        import yt_dlp
    except ImportError:
        print(f"\r❌ yt-dlp tidak terinstal.{' '*40}", flush=True)
        return False

    ydl_opts = {
        'cookiesfrombrowser': (browser_name,),
        'cookiefile': output_path,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info("https://www.youtube.com", download=False)
        
        if os.path.exists(output_path):
            print(f"\r✅ Cookies berhasil diperbarui!{' '*40}", flush=True)
            return True
        else:
            print(f"\r❌ Gagal mengekstrak cookies.{' '*40}", flush=True)
            return False
            
    except Exception as e:
        print(f"\r❌ Gagal mengekstrak cookies.{' '*40}", flush=True)
        err_msg = str(e)
        if "Permission denied" in err_msg or "locked" in err_msg:
            print(f"   ⚠️  Database browser terkunci. Coba TUTUP {browser_name} sepenuhnya dan coba lagi.")
        elif "no cookies found" in err_msg.lower():
            print(f"   ⚠️  Tidak ada cookie YouTube yang ditemukan. Pastikan Anda sudah login ke YouTube di {browser_name} dan coba lagi.")
        else:
            logging.error(f"Detail Error Cookies: {err_msg}")
        return False

def setup_paths() -> SimpleNamespace:
    """
    Mendeteksi path dasar dan mengkonfigurasi semua path yang dibutuhkan oleh aplikasi.
    Juga melakukan validasi awal untuk folder/file penting.
    """
    # Deteksi apakah berjalan sebagai script python biasa atau exe (frozen)
    env_base = os.getenv('YT_TOOLKIT_BASE_DIR')
    if env_base:
        BASE_DIR = Path(env_base)
    elif getattr(sys, 'frozen', False):
        BASE_DIR = Path(sys.executable).parent
    else:
        # utils.py ada di yt_toolkit/core/, jadi butuh naik 3 level ke root project
        BASE_DIR = Path(__file__).parent.parent.parent.resolve()

    paths = SimpleNamespace()
    paths.BASE_DIR = BASE_DIR
    
    # Struktur Folder Temp Baru
    paths.TEMP_DIR = BASE_DIR / "temp"
    paths.TEMP_SUMMARIZE = paths.TEMP_DIR / "summarize"
    paths.TEMP_VIDEO = paths.TEMP_DIR / "video_handling"
    paths.TEMP_FINAL = paths.TEMP_DIR / "final"
    
    paths.FONTS_DIR = BASE_DIR / "fonts"
    paths.MODELS_DIR = BASE_DIR / "models"
    paths.DETECTOR_MODEL_PATH = paths.MODELS_DIR / "detector.tflite"
    
    # Path Terpusat Tambahan
    paths.COOKIES_DIR = BASE_DIR / "cookies"
    paths.LOG_FILE = BASE_DIR / "debug.log"
    paths.ENV_FILE = BASE_DIR / ".env"
    paths.CONFIG_FILE = BASE_DIR / "config.yaml"
    paths.PROMPT_FILE = BASE_DIR / "yt_toolkit" / "ai" / "gemini_prompt.txt"
    paths.USER_DOWNLOADS_DIR = BASE_DIR
    
    # Inject bin folder to PATH automatically
    bin_path = str(BASE_DIR / "bin")
    if bin_path not in os.environ['PATH']:
        os.environ['PATH'] = bin_path + os.pathsep + os.environ['PATH']
        logging.info(f"Runtime PATH Injection: {bin_path}")

    # Buat folder temp utama
    paths.TEMP_SUMMARIZE.mkdir(parents=True, exist_ok=True)
    paths.TEMP_VIDEO.mkdir(parents=True, exist_ok=True)
    paths.TEMP_FINAL.mkdir(parents=True, exist_ok=True)

    # Validasi Path
    if not paths.FONTS_DIR.exists():
        logging.warning(f"⚠️ Folder fonts tidak ditemukan di: {paths.FONTS_DIR}.")
    if not paths.DETECTOR_MODEL_PATH.exists():
        logging.warning(f"⚠️ Model detector.tflite tidak ditemukan di: {paths.DETECTOR_MODEL_PATH}.")

    return paths