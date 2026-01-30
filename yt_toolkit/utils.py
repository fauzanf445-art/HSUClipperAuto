import subprocess
import re
import logging
import sys
import os
from typing import List, Optional, Tuple
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path

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
def get_duration(file_path: str, ffprobe_path: str = "ffprobe") -> float:
    """Mendapatkan durasi file media dalam detik untuk perhitungan progres."""
    cmd = [
        ffprobe_path, '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file_path
    ]
    try:
        return float(subprocess.check_output(cmd).decode('utf-8').strip())
    except Exception as e:
        logging.warning(f"Gagal mendapatkan durasi untuk {file_path}: {e}")
        return 0.0

def get_video_resolution(video_path: str, ffprobe_path: str = "ffprobe") -> Tuple[int, int]:
    """Mendapatkan resolusi asli video (lebar, tinggi) menggunakan ffprobe."""
    cmd = [
        ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
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

def run_ffmpeg_with_progress(cmd: List[str], total_duration: float, task_name: str):
    """Menjalankan perintah FFmpeg dan menampilkan progress bar."""
    if total_duration <= 0:
        # Fallback ke mode senyap jika durasi tidak diketahui
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg command failed (duration=0). Command: {' '.join(e.cmd)}. Error: {e.stderr}")
            raise
        return

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
                print(f"\r{task_name}: [{bar}{spaces}] {percent}%{' '*20}", end='', flush=True)

    process.wait()
    print('\r', end='', flush=True)
    if process.returncode != 0:
        error_log = "".join(stderr_output[-20:])
        logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
        raise subprocess.CalledProcessError(process.returncode, cmd, stderr="".join(stderr_output))

def update_cookies_from_browser(browser_name: str, output_path: str) -> bool:
    """
    Mengekstrak cookies dari browser dan menyimpannya ke file.
    Membutuhkan browser untuk ditutup (terkadang) agar database tidak terkunci.
    """
    print(f"⏳ Mengekstrak cookies dari {browser_name} ke {os.path.basename(output_path)}...", end='\r', flush=True)
    
    # Gunakan modul yt_dlp via python saat ini untuk memastikan kompatibilitas env
    # Format: python -m yt_dlp --cookies-from-browser [browser] --cookies [file] --skip-download [url_dummy]
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--cookies-from-browser", browser_name,
        "--cookies", output_path,
        "--skip-download",
        "https://www.youtube.com" # URL dummy pemicu
    ]
    
    try:
        # Jalankan perintah dan tangkap outputnya
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"\r✅ Cookies berhasil diperbarui!{' '*40}", flush=True)
            return True
        else:
            print(f"\r❌ Gagal mengekstrak cookies.{' '*40}", flush=True)
            # Filter pesan error umum untuk memberikan saran yang berguna
            err_msg = result.stderr
            if "Permission denied" in err_msg or "locked" in err_msg:
                print(f"   ⚠️  Database browser terkunci. Coba TUTUP {browser_name} sepenuhnya dan coba lagi.")
            elif "no cookies found" in err_msg.lower():
                print(f"   ⚠️  Tidak ada cookie YouTube yang ditemukan. Pastikan Anda sudah login ke YouTube di {browser_name} dan coba lagi.")
            else:
                logging.error(f"Detail Error Cookies: {err_msg}")
            return False
            
    except Exception as e:
        print(f"\r❌ Terjadi kesalahan sistem: {e}{' '*30}", flush=True)
        return False

def detect_scene_changes(video_path: str, threshold: float = 0.3, ffmpeg_path: str = "ffmpeg") -> List[float]:
    """
    Mendeteksi timestamp (detik) dimana terjadi pergantian scene drastis menggunakan FFmpeg.
    
    Args:
        threshold (float): Sensitivitas (0.0 - 1.0). 
                           0.3 adalah standar yang bagus. Semakin kecil semakin sensitif.
    Returns:
        List[float]: Daftar waktu (detik) terjadinya pergantian scene.
    """
    cmd = [
        ffmpeg_path, 
        '-i', video_path,
        '-vf', f"select='gt(scene,{threshold})',showinfo",
        '-f', 'null',
        '-'
    ]
    
    timestamps = []
    try:
        # FFmpeg menulis info scene ke stderr, bukan stdout
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        # Regex untuk menangkap pts_time dari log showinfo
        # Contoh log: [Parsed_showinfo_1 @ ...] n: 1 pts: 12345 pts_time:0.417000 ...
        regex = r"pts_time:([0-9.]+)"
        
        for line in process.stderr.split('\n'):
            if "showinfo" in line and "pts_time" in line:
                match = re.search(regex, line)
                if match:
                    timestamps.append(float(match.group(1)))
                    
    except Exception as e:
        logging.error(f"Gagal mendeteksi scene change: {e}")
        
    return timestamps

def setup_paths() -> SimpleNamespace:
    """
    Mendeteksi path dasar dan mengkonfigurasi semua path yang dibutuhkan oleh aplikasi.
    Juga melakukan validasi awal untuk folder/file penting.
    """
    # Deteksi apakah berjalan sebagai script python biasa atau exe (frozen)
    if getattr(sys, 'frozen', False):
        BASE_DIR = Path(sys.executable).parent
    else:
        # Asumsi utils.py ada di dalam folder yt_toolkit
        BASE_DIR = Path(__file__).parent.parent.resolve()

    paths = SimpleNamespace()
    paths.BASE_DIR = BASE_DIR
    paths.OUTPUT_DIR = BASE_DIR / "output"
    paths.RAW_ASSETS_DIR = paths.OUTPUT_DIR / "raw_assets"
    paths.FINAL_OUTPUT_DIR = paths.OUTPUT_DIR / "final_output"
    paths.FONTS_DIR = BASE_DIR / "fonts"
    paths.MODELS_DIR = BASE_DIR / "models"
    paths.DETECTOR_MODEL_PATH = paths.MODELS_DIR / "detector.tflite"
    paths.BIN_DIR = BASE_DIR / "bin"
    
    # Buat folder output utama
    paths.RAW_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # Validasi Path
    if not paths.FONTS_DIR.exists():
        logging.warning(f"⚠️ Folder fonts tidak ditemukan di: {paths.FONTS_DIR}.")
    if not paths.DETECTOR_MODEL_PATH.exists():
        logging.warning(f"⚠️ Model detector.tflite tidak ditemukan di: {paths.DETECTOR_MODEL_PATH}.")
    if not paths.BIN_DIR.exists():
        logging.warning(f"⚠️ Folder 'bin' tidak ditemukan di: {paths.BIN_DIR}.")

    # Konfigurasi Path Tools dengan Fallback
    paths.FFMPEG_PATH = str(paths.BIN_DIR / "ffmpeg.exe") if (paths.BIN_DIR / "ffmpeg.exe").exists() else "ffmpeg"
    paths.FFPROBE_PATH = str(paths.BIN_DIR / "ffprobe.exe") if (paths.BIN_DIR / "ffprobe.exe").exists() else "ffprobe"
    paths.DENO_PATH = str(paths.BIN_DIR / "deno.exe") if (paths.BIN_DIR / "deno.exe").exists() else "deno"
    
    # Validasi Kritis: Pastikan FFmpeg tersedia karena merupakan dependensi utama.
    if not is_tool_available(paths.FFMPEG_PATH):
        raise FileNotFoundError(
            "❌ FFmpeg tidak ditemukan! Program tidak dapat berjalan.\n"
            f"   👉 Solusi 1: Pastikan FFmpeg terinstal dan ada di PATH sistem Anda.\n"
            f"   👉 Solusi 2: Unduh FFmpeg dan letakkan 'ffmpeg.exe' di dalam folder: {paths.BIN_DIR}"
        )

    return paths