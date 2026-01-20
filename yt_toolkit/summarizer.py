import os
import re
import json
import logging
import time
import subprocess
from typing import Optional

# Mencoba mengimpor library yang dibutuhkan
try:
    from google import genai
except ImportError:
    genai = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

class Summarize:
    """Class untuk mengambil transkrip YouTube dan merangkumnya menggunakan Google Gemini."""
    
    def __init__(self, api_key: Optional[str], out_dir: str, ffmpeg_path: str = "ffmpeg", model: str = 'gemini-flash-latest'):
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

        # Load prompt from external file for easier maintenance
        prompt_path = os.path.join(os.path.dirname(__file__), 'gemini_prompt.txt')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                self.instruction_prompt_template = f.read()
        except FileNotFoundError:
            raise RuntimeError(f"Prompt file not found at {prompt_path}")

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Mengekstrak ID video 11 karakter dari URL YouTube."""
        regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        m = re.search(regex, url)
        return m.group(1) if m else None

    def get_transcript(self, video_url: str, prefer_langs=('id', 'en')) -> str:
        """Mengambil teks transkrip dari YouTube berdasarkan bahasa yang dipilih."""
        if YouTubeTranscriptApi is None:
            raise RuntimeError('Library "youtube-transcript-api" belum terinstal.')
            
        video_id = self.extract_video_id(video_url)
        if not video_id:
            raise ValueError(f'URL YouTube tidak valid: {video_url}')

        last_exc = None
        for lang in prefer_langs:
            try:
                result = YouTubeTranscriptApi().fetch(video_id, languages=[lang])
                raw = result.to_raw_data()
                full_text = '\n'.join([f"[{item['start']}] {item['text']}" for item in raw])
                return full_text
            except Exception as e:
                last_exc = e
                continue
        raise RuntimeError(f'Failed to fetch transcript. Detail: {last_exc}')

    
    def get_audio(self, a_path: str) -> Optional[str]:
        """Konversi audio asli ke MP3 ringan untuk dikirim ke Gemini."""
        if not a_path or not os.path.exists(a_path):
            logging.error(f"File audio asli tidak ditemukan: {a_path}")
            return None

        # Tentukan nama file baru agar tidak menimpa yang asli
        base_dir = os.path.dirname(a_path)
        gemini_audio_path = os.path.join(base_dir, "audio_for_gemini.mp3")

        # Jika sudah ada, langsung gunakan (efisiensi)
        if os.path.exists(gemini_audio_path):
            return gemini_audio_path

        print(f"⏳ Mengonversi audio ke MP3 ringan untuk AI...")
        try:
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', a_path,
                '-vn',              # Tanpa video
                '-ar', '44100',      # Sample rate standar
                '-ac', '2',          # Stereo
                '-b:a', '128k',      # Bitrate ringan agar upload cepat
                gemini_audio_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return gemini_audio_path
        except Exception as e:
            logging.error(f"Gagal konversi audio ke MP3: {e}")
            return a_path

    def generate_summarize(self, transcript_text: str, video_url: str, audio_path: str) -> str:
        """Mengirim transkrip dan audio ke Gemini AI untuk analisis momen klip."""
        
        # 1. Inisialisasi daftar konten dengan prompt teks dari template
        instruction_prompt = self.instruction_prompt_template.format(
            transcript_text=transcript_text,
            video_url=video_url
        )
        
        contents = [
            instruction_prompt,f"TRANSCRIPT TEXT DATA:\n{transcript_text}"]

        path_to_upload = self.get_audio(audio_path) or audio_path
        audio_file_obj = None

        for attempt in range(3):
            try:
                print(f"⏳ Uploading audio (Attempt {attempt + 1}/3): {os.path.basename(path_to_upload)}...")
                uploaded = self.client.files.upload(file=path_to_upload)
                
                # Tunggu hingga status ACTIVE (Polling)
                print("⏳ Menunggu file audio ACTIVE...")
                while uploaded.state.name == "PROCESSING":
                    time.sleep(3)
                    uploaded = self.client.files.get(name=uploaded.name)
                
                if uploaded.state.name == "ACTIVE":
                    audio_file_obj = uploaded
                    print("✅ Audio siap dianalisis.")
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
            logging.info("Mengirim data ke Gemini untuk analisis...")
            response = self.client.models.generate_content(
                model=self.model, 
                contents=contents,
                config={'response_mime_type': 'application/json'}
            )
            return response.text
        except Exception as e:
            logging.error(f"Gagal generate summary dari Gemini: {e}")
            raise

    def save_summary(self, video_url: str, summary_text: str, transcript_text: Optional[str] = None, target_dir: Optional[str] = None) -> str:
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

        # Gunakan target_dir jika ada (agar satu folder dengan audio/video), jika tidak gunakan default (ID)
        if target_dir:
            video_dir = target_dir
        else:
            video_id = self.extract_video_id(video_url) or 'unknown'
            video_dir = os.path.join(self.out_dir, video_id)
        os.makedirs(video_dir, exist_ok=True)
        
        clips_path = os.path.join(video_dir, 'transcripts.json')
        with open(clips_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
            
        if transcript_text:
            with open(os.path.join(video_dir, 'transcript.txt'), 'w', encoding='utf-8') as f:
                f.write(transcript_text)
                
        return clips_path