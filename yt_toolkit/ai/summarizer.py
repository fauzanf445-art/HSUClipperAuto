import os
import json
import logging
import time
from typing import Optional
from yt_toolkit.core.utils import setup_paths, print_progress

# Mencoba mengimpor library yang dibutuhkan
try:
    from google import genai
except ImportError:
    genai = None

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
        except Exception as e:
            # Log error spesifik untuk debugging di file log, tanpa menampilkannya ke user.
            logging.error(f"Validasi API Key gagal: {e}")
            return False

    def __init__(self, api_key: Optional[str], out_dir: str, model: str = 'gemini-flash-latest'):
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

        # Load prompt from external file for easier maintenance
        prompt_path = setup_paths().PROMPT_FILE
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.instruction_prompt_template = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Prompt file not found at {prompt_path}")

    def generate_summarize(self, transcript_text: str, video_url: str, audio_path: str) -> str:
        """Mengirim transkrip dan audio ke Gemini AI untuk analisis momen klip."""
        
        # 1. Inisialisasi daftar konten dengan prompt teks dari template
        instruction_prompt = self.instruction_prompt_template.format(
            transcript_text=transcript_text,
            video_url=video_url
        )
        
        contents = [
            instruction_prompt,
            f"TRANSCRIPT TEXT DATA:\n{transcript_text}"
        ]

        path_to_upload = audio_path
        audio_file_obj = None

        for attempt in range(3):
            try:
                print_progress(10 + (attempt * 10), "Upload Audio", f"Attempt {attempt + 1}/3")
                uploaded = self.client.files.upload(file=path_to_upload)
                
                print_progress(40, "Processing Audio", "Server Gemini")
                # --- POLLING ---: Tunggu hingga server Gemini selesai memproses audio.
                while uploaded.state.name == "PROCESSING":
                    time.sleep(3)
                    uploaded = self.client.files.get(name=uploaded.name)
                
                if uploaded.state.name == "ACTIVE":
                    audio_file_obj = uploaded
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
            print_progress(60, "Analisis Konten", "Gemini AI")
            response = self.client.models.generate_content(
                model=self.model, 
                contents=contents,
                config={'response_mime_type': 'application/json'}
            )
            
            if not response.text:
                logging.warning("Respon Gemini kosong atau None (Mungkin terkena Safety Filter). Mengembalikan JSON kosong.")
                return "{}"
            return response.text
        except Exception as e:
            logging.error(f"Gagal generate summary dari Gemini: {e}")
            raise

    def save_summary(self, summary_text: str, transcript_text: Optional[str] = None, target_dir: str = None) -> str:
        """Menyimpan hasil summary ke file transcripts.json."""
        
        if summary_text is None:
            logging.warning("summary_text bernilai None. Menggunakan default '{}' untuk mencegah crash.")
            summary_text = "{}"

        # Membersihkan format markdown jika AI secara keliru membungkus output JSON dengan ```json ... ```
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