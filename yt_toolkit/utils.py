import subprocess
import re
import logging
from typing import List

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
                print(f"\r{task_name}: [{bar}{spaces}] {percent}%", end='', flush=True)

    process.wait()
    print('\r', end='', flush=True)
    if process.returncode != 0:
        error_log = "".join(stderr_output[-20:])
        logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
        raise subprocess.CalledProcessError(process.returncode, cmd, stderr="".join(stderr_output))