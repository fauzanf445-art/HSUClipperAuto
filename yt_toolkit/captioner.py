import os
import subprocess
import logging
from faster_whisper import WhisperModel, download_model, BatchedInferencePipeline
from pathlib import Path
import re
from typing import List

# Import utilitas umum
from .utils import get_duration, run_ffmpeg_with_progress

class VideoCaptioner:
    """
    Class untuk menghasilkan dan 'membakar' (burn-in) subtitle ke dalam video.
    Menggunakan faster-whisper untuk transkripsi AI dan FFmpeg untuk rendering video.
    """
    def __init__(self, model_size="large-v3-turbo", device="cpu", compute_type="int8", download_root="./models", ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"):
        """
        Inisialisasi model Whisper.
        - model_size: Ukuran model yang akan digunakan (misal: "large-v3").
        - device: Perangkat untuk inferensi ('cuda' atau 'cpu').
        - compute_type: Tipe kuantisasi model ('float16', 'int8') untuk menghemat memori.
        - download_root: Folder untuk menyimpan file model AI.
        """
        if not os.path.exists(download_root):
            os.makedirs(download_root)

        self.model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            local_files_only=False
        )
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def get_video_resolution(self, video_path):
        """Mendapatkan resolusi asli video menggunakan ffprobe secara otomatis."""
        cmd = [
            self.ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
            video_path
        ]
        result = subprocess.check_output(cmd).decode('utf-8').strip().split('x')
        return int(result[0]), int(result[1])

    def _get_ass_style(self, w, h, alignment=2):
        """Mengatur tampilan teks adaptif berdasarkan resolusi layar."""
        # Logika styling adaptif: Ukuran font dan margin dihitung secara proporsional
        # terhadap tinggi video (h). Ini memastikan subtitle terlihat bagus di berbagai resolusi.
        font_size = int(h * 0.07)               # Font size dihitung proporsional (7% dari tinggi layar)
        outline_size = int(font_size * 0.05)    # Set ke 0 untuk menghapus outline. Gunakan int(font_size * 0.05) untuk tipis.
        margin_v = int(h * 0.15)                # MarginV: Jarak dari bawah. 15% dari tinggi layar (aman dari UI TikTok/Reels)

        # Header format ASS (Advanced SubStation Alpha)
        # PrimaryColour: Warna teks utama (putih)
        # OutlineColour: Warna garis tepi (hitam)
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Poppins,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{outline_size},2,{alignment},10,10,{margin_v},1
"""

    def _format_timestamp_ass(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02}:{secs:05.2f}"

    def generate_styled_ass(self, video_path, alignment=2):
        """Transkripsi dengan gaya kata-per-kata dan highlight otomatis."""
        width, height = self.get_video_resolution(video_path)

        total_duration = get_duration(video_path, self.ffprobe_path)
        segments, _ = self.model.transcribe(video_path, word_timestamps=True, vad_filter=True)
        
        ass_path = video_path.replace(Path(video_path).suffix, ".ass")
        header = self._get_ass_style(width, height, alignment)
        
        print(f"   ⏳ Mentranskripsi (AI): 0%", end="\r")

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            for segment in segments:
                if total_duration > 0:
                    percent = int((segment.end / total_duration) * 100)
                    print(f"   ⏳ Mentranskripsi (AI): {percent}%", end="\r")

                # --- LOGIKA ANIMASI KATA-PER-KATA ---
                words = segment.words
                # Mengambil per 2 kata agar subtitle tidak terlalu panjang dan lebih dinamis.
                for i in range(0, len(words), 2):
                    chunk = words[i:i + 2]
                    start = self._format_timestamp_ass(chunk[0].start)
                    end = self._format_timestamp_ass(chunk[-1].end)
                    
                    # Logika Highlight: Kata pertama Kuning (\1c&H00FFFF&), Kata kedua Putih (\1c&HFFFFFF&)
                    if len(chunk) > 1:
                        word1 = chunk[0].word.strip().upper()
                        word2 = chunk[1].word.strip().upper()
                        text_content = f"{{\\1c&H00FFFF&}}{word1} {{\\1c&HFFFFFF&}}{word2}"
                    else:
                        text_content = f"{{\\1c&H00FFFF&}}{chunk[0].word.strip().upper()}"
                    
                    # Efek Animasi "Elastic Pop" menggunakan tag ASS:
                    # {\fscx80\fscy80} -> Mulai dengan ukuran 80%
                    # {\t(0,80,\fscx115\fscy115)} -> Dalam 80ms, animasi ke ukuran 115%
                    # {\t(80,150,\fscx100\fscy100)} -> Dari 80ms ke 150ms, animasi kembali ke ukuran normal 100%
                    animated_text = f"{{\\fscx80\\fscy80\\t(0,80,\\fscx115\\fscy115)\\t(80,150,\\fscx100\\fscy100)}}{text_content}"
                    f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{animated_text}\n")
        
        print(f"\r{' '*50}\r", end="") # Hapus baris progres
        return ass_path

    def transcribe_for_ai(self, audio_path):
        """Transkripsi audio mentah untuk keperluan summarization (fallback jika tidak ada CC)."""
        logging.info(f"Mulai transkripsi audio untuk summary: {audio_path}")

        total_duration = get_duration(audio_path, self.ffprobe_path)
        
        # Menggunakan Batched Pipeline untuk kecepatan ekstra pada audio panjang
        batched_model = BatchedInferencePipeline(model=self.model)
        segments, _ = batched_model.transcribe(audio_path, beam_size=5, batch_size=16)
        
        full_text = []
        print(f"⏳ Transkripsi Manual: 0%", end="\r")
        
        for segment in segments:
            start = round(segment.start, 2)
            text = segment.text.strip()
            full_text.append(f"[{start}] {text}")
            
            if total_duration > 0:
                percent = int((segment.end / total_duration) * 100)
                print(f"⏳ Transkripsi Manual: {percent}%", end="\r")
            
        print(f"✅ Transkripsi Manual: 100%      ")
        return "\n".join(full_text)

    def process_full_caption(self, video_path, final_path, fonts_dir, use_gpu=False):
        """Membakar subtitle ke video dengan dukungan font lokal."""
        ass_path = self.generate_styled_ass(video_path)
        
        # Penyesuaian path untuk filtergraph FFmpeg di Windows.
        # Karakter ':' dan '\' adalah karakter spesial dan harus di-escape dengan benar.
        # Contoh: 'C:\path' menjadi 'C\:\\path' agar FFmpeg tidak salah interpretasi.
        clean_ass = ass_path.replace('\\', '\\\\').replace(':', '\\:')
        clean_fonts = str(fonts_dir).replace('\\', '\\\\').replace(':', '\\:')
        
        # Konfigurasi CPU (libx264)
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', video_path,
            '-vf', f"subtitles=filename='{clean_ass}':fontsdir='{clean_fonts}'",
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '20',
            '-c:a', 'copy',
            final_path
        ]
        duration = get_duration(video_path, self.ffprobe_path)

        try:
            run_ffmpeg_with_progress(cmd, duration, f"   🔥 Membakar Caption (CPU)...")

            if os.path.exists(ass_path):
                os.remove(ass_path)
            return True
        except Exception as e:
            logging.error(f"Gagal burning subtitle: {e}")
            return False