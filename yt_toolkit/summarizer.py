import os
import re
import json
import logging
import time
import subprocess
import urllib.request
from typing import Optional, List

# Mencoba mengimpor library yang dibutuhkan
try:
    from google import genai
except ImportError:
    genai = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

class Summarize:
    """Class untuk mengambil transkrip YouTube dan merangkumnya menggunakan Google Gemini."""
    
    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """Memvalidasi apakah API Key berfungsi dengan melakukan request ringan."""
        if genai is None:
            print("❌ Library google-genai tidak terinstal.")
            return False
        
        try:
            client = genai.Client(api_key=api_key)
            # Mencoba mengambil satu model untuk memverifikasi otentikasi
            next(iter(client.models.list(config={'page_size': 1})), None)
            return True
        except Exception:
            return False

    def __init__(self, api_key: Optional[str], out_dir: str, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe", model: str = 'gemini-flash-latest'):
        # Mengambil API Key dari parameter atau environment variable
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        if not self.api_key:
            raise RuntimeError('API Key Gemini tidak ditemukan. Pastikan sudah diatur di .env atau parameter.')
        
        if genai is None:
            raise RuntimeError('Package "google-genai" belum terinstal.')

        # Inisialisasi Client Gemini
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        
        # Pengaturan direktori output
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        # Load prompt from external file for easier maintenance
        prompt_path = os.path.join(os.path.dirname(__file__), 'gemini_prompt.txt')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.instruction_prompt_template = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Prompt file not found at {prompt_path}")

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
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return

        cmd = [arg for arg in cmd if arg not in ['-stats']]

        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True, encoding='utf-8', errors='ignore')

        for line in process.stderr:
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
            raise subprocess.CalledProcessError(process.returncode, cmd)

    def get_transcript(self, video_url: str, prefer_langs=('id', 'en'), audio_path: Optional[str] = None, captioner=None) -> str:
        """Mengambil teks transkrip dari YouTube atau fallback ke manual transcription."""
        
        # 1. Coba ambil menggunakan yt-dlp (Metode Utama)
        if yt_dlp:
            try:
                print("⏳ Mengambil transkrip (yt-dlp)...", end='\r', flush=True)
                ydl_opts = {
                    'skip_download': True,  # Kita hanya butuh metadata
                    'quiet': True,
                    'no_warnings': True,
                    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    
                    # Gabungkan subtitle manual dan otomatis
                    subtitles = info.get('subtitles') or {}
                    auto_captions = info.get('automatic_captions') or {}
                    all_subs = {**auto_captions, **subtitles}

                    target_url = None
                    
                    # Cari bahasa yang cocok
                    for lang in prefer_langs:
                        if lang in all_subs:
                            # Cari format json3 (paling mudah diparsing)
                            for fmt in all_subs[lang]:
                                if fmt.get('ext') == 'json3':
                                    target_url = fmt['url']
                                    break
                        if target_url: break
                    
                    if target_url:
                        # Download konten JSON3 langsung dari URL YouTube
                        with urllib.request.urlopen(target_url) as response:
                            data = json.loads(response.read().decode())
                        
                        # Parsing JSON3 ke format teks [timestamp] text
                        full_text = []
                        for event in data.get('events', []):
                            # Ambil segmen teks jika ada
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

        # 2. Fallback ke AI Captioner (Whisper) jika yt-dlp gagal atau tidak ada CC
        if audio_path and captioner:
            print("⚠️ Tidak ada CC. Menggunakan Fallback AI (Whisper)...", end='\r', flush=True)
            return captioner.transcribe_for_ai(audio_path)

        raise RuntimeError('Gagal mendapatkan transkrip (yt-dlp gagal dan audio path tidak tersedia).')

    def generate_summarize(self, transcript_text: str, video_url: str, audio_path: str) -> str:
        """Mengirim transkrip dan audio ke Gemini AI untuk analisis momen klip."""
        
        # 1. Inisialisasi daftar konten dengan prompt teks dari template
        instruction_prompt = self.instruction_prompt_template.format(
            transcript_text=transcript_text,
            video_url=video_url
        )
        
        contents = [
            instruction_prompt,f"TRANSCRIPT TEXT DATA:\n{transcript_text}"]

        path_to_upload = audio_path
        audio_file_obj = None

        for attempt in range(3):
            try:
                print(f"\r⏳ Uploading audio ke Gemini ({attempt + 1}/3)...{' '*20}", end='', flush=True)
                uploaded = self.client.files.upload(file=path_to_upload)
                
                # Tunggu hingga status ACTIVE (Polling)
                print(f"\r⏳ Memproses audio di server Gemini...{' '*20}", end='', flush=True)
                while uploaded.state.name == "PROCESSING":
                    time.sleep(3)
                    uploaded = self.client.files.get(name=uploaded.name)
                
                if uploaded.state.name == "ACTIVE":
                    audio_file_obj = uploaded
                    # print("✅ Audio siap dianalisis.") # [CLEANUP] Tidak perlu print baris baru
                    break
                        
            except Exception as e:
                if "disconnected" in str(e).lower() and attempt < 2:
                    print(f"⚠️ Koneksi terputus, mencoba ulang dalam 5 detik...")
                    time.sleep(5)
                    continue
                else:
                    logging.error(f"Gagal mengunggah audio: {e}")
                    print("⚠️ Analisis dilanjutkan hanya dengan teks.")
                    break
        
        # 4. Tambahkan Audio ke list contents jika berhasil upload
        if audio_file_obj:
            contents.append("AUDIO FILE DATA (LISTEN TO THIS FOR ENERGY ANALYSIS):")
            contents.append(audio_file_obj)
        
        # 3. Kirim ke Gemini
        try:
            print(f"\r⏳ Menganalisa konten (Gemini AI)...{' '*30}", end='', flush=True)
            response = self.client.models.generate_content(
                model=self.model, 
                contents=contents,
                config={'response_mime_type': 'application/json'}
            )
            return response.text
        except Exception as e:
            logging.error(f"Gagal generate summary dari Gemini: {e}")
            raise

    def save_summary(self, video_url: str, summary_text: str, transcript_text: Optional[str] = None, target_dir: str = None) -> str:
        """Menyimpan hasil summary ke file transcripts.json."""
        
        # Membersihkan format markdown jika AI memberikan ```json ... ```
        clean_json = summary_text.strip()
        if clean_json.startswith("```"):
            lines = clean_json.splitlines()
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            clean_json = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_json)
        except json.JSONDecodeError:
            logging.error("Gagal melakukan parsing JSON dari AI.")
            parsed = {'video_title': 'Unknown', 'clips': [], 'raw_error': summary_text}

        # WAJIB: Gunakan target_dir dari downloader agar konsisten (Judul-ID)
        if not target_dir:
            raise ValueError("Parameter 'target_dir' wajib diisi agar lokasi file konsisten dengan Downloader.")
            
        video_dir = target_dir
        os.makedirs(video_dir, exist_ok=True)
        
        clips_path = os.path.join(video_dir, 'transcripts.json')
        with open(clips_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
            
        if transcript_text:
            with open(os.path.join(video_dir, 'transcript.txt'), 'w', encoding='utf-8') as f:
                f.write(transcript_text)
                
        return clips_path