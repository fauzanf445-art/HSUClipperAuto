import os
import subprocess
import logging
from faster_whisper import WhisperModel, download_model, BatchedInferencePipeline
from pathlib import Path
import re
from typing import List

class VideoCaptioner:
    def __init__(self, model_size="large-v3-turbo", device="cpu", compute_type="int8", download_root="./models", ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"):
        if not os.path.exists(download_root):
            os.makedirs(download_root)

        download_model(model_size, output_dir=download_root)

        self.model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            local_files_only=False
        )
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

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

    def get_duration(self, file_path):
        """Mendapatkan durasi file media dalam detik untuk perhitungan progres."""
        cmd = [
            self.ffprobe_path, '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            file_path
        ]
        try:
            return float(subprocess.check_output(cmd).decode('utf-8').strip())
        except Exception as e:
            logging.warning(f"Gagal mendapatkan durasi: {e}")
            return 0.0

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
        font_size = int(h * 0.07)               # Font size dihitung proporsional (7% dari tinggi layar)
        outline_size = int(font_size * 0.05)    # Set ke 0 untuk menghapus outline. Gunakan int(font_size * 0.05) untuk tipis.
        margin_v = int(h * 0.15)                # MarginV: Jarak dari bawah. 15% dari tinggi layar (aman dari UI TikTok/Reels)


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
        
        total_duration = self.get_duration(video_path)
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

                words = segment.words
                # Mengambil per 2 kata agar transkripsi dinamis
                for i in range(0, len(words), 2):
                    chunk = words[i:i + 2]
                    start = self._format_timestamp_ass(chunk[0].start)
                    end = self._format_timestamp_ass(chunk[-1].end)
                    
                    # Logika Highlight: Kata pertama Kuning, Kata kedua Putih
                    if len(chunk) > 1:
                        word1 = chunk[0].word.strip().upper()
                        word2 = chunk[1].word.strip().upper()
                        text_content = f"{{\\1c&H00FFFF&}}{word1} {{\\1c&HFFFFFF&}}{word2}"
                    else:
                        text_content = f"{{\\1c&H00FFFF&}}{chunk[0].word.strip().upper()}"
                    
                    # Efek Elastic Pop: Kecil (80%) -> Besar (115%) -> Normal (100%)
                    # Memberikan kesan teks yang "muncul" dengan energi (bouncy)
                    animated_text = f"{{\\fscx80\\fscy80\\t(0,80,\\fscx115\\fscy115)\\t(80,150,\\fscx100\\fscy100)}}{text_content}"
                    f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{animated_text}\n")
        
        print(f"\r{' '*50}\r", end="") # Hapus baris progres
        return ass_path

    def transcribe_for_ai(self, audio_path):
        """Transkripsi audio mentah untuk keperluan summarization (fallback jika tidak ada CC)."""
        logging.info(f"Mulai transkripsi audio untuk summary: {audio_path}")
        
        total_duration = self.get_duration(audio_path)
        
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

    def process_full_caption(self, video_path, final_path, fonts_dir, use_gpu=True):
        """Membakar subtitle ke video dengan dukungan font lokal."""
        ass_path = self.generate_styled_ass(video_path)
        
        # Penyesuaian path untuk filtergraph FFmpeg di Windows.
        # Karakter ':' dan '\' adalah karakter spesial dan harus di-escape dengan benar.
        # Contoh: 'C:\path' menjadi 'C\:\\path'
        clean_ass = ass_path.replace('\\', '\\\\').replace(':', '\\:')
        clean_fonts = str(fonts_dir).replace('\\', '\\\\').replace(':', '\\:')
        
        def run_ffmpeg(is_gpu):
            video_codec = 'h264_nvenc' if is_gpu else 'libx264'
            preset = 'p4' if is_gpu else 'ultrafast'
            
            cmd = [
                self.ffmpeg_path, '-y',
                '-i', video_path,
                '-vf', f"subtitles=filename='{clean_ass}':fontsdir='{clean_fonts}'",
                '-c:v', video_codec,
                '-preset', preset
            ]

            if is_gpu:
                cmd.extend(['-rc', 'constqp', '-qp', '23'])
            else:
                cmd.extend(['-crf', '20'])

            cmd.extend([
                '-c:a', 'copy',
                final_path
            ])
            duration = self.get_duration(video_path)
            self._run_ffmpeg_with_progress(cmd, duration, f"   🔥 Membakar Caption...")

        try:
            try:
                run_ffmpeg(use_gpu) # Coba dengan GPU
            except subprocess.CalledProcessError:
                if use_gpu:
                    logging.warning("⚠️ NVENC (GPU) gagal. Mencoba fallback ke CPU (libx264)...")
                    run_ffmpeg(False)
                else:
                    raise

            if os.path.exists(ass_path):
                os.remove(ass_path)
            return True
        except Exception as e:
            logging.error(f"Gagal burning subtitle: {e}")
            return False