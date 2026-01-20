import os
import subprocess
import logging
from faster_whisper import WhisperModel, download_model
from pathlib import Path

class VideoCaptioner:
    def __init__(self, model_size="large-v3-turbo", device="cpu", compute_type="int8", download_root="./models", ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"):
        if not os.path.exists(download_root):
            os.makedirs(download_root)

        logging.info(f"Memeriksa model {model_size}...")
        download_model(model_size, output_dir=download_root)

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

    def _get_ass_style(self, w, h, alignment=5):
        """Mengatur tampilan teks adaptif berdasarkan resolusi layar."""
        # Font size dihitung proporsional (7% dari tinggi layar)
        font_size = int(h * 0.07)
        outline_size = int(font_size * 0.12)
        # MarginV ditempatkan di area tengah-bawah (25% dari tinggi layar)
        margin_v = int(h * 0.25)

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

    def generate_styled_ass(self, video_path, alignment=5):
        """Transkripsi dengan gaya kata-per-kata dan highlight otomatis."""
        width, height = self.get_video_resolution(video_path)
        logging.info(f"Resolusi terdeteksi: {width}x{height}. Memulai transkripsi...")
        
        segments, _ = self.model.transcribe(video_path, word_timestamps=True, vad_filter=True)
        
        ass_path = video_path.replace(Path(video_path).suffix, ".ass")
        header = self._get_ass_style(width, height, alignment)

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            for segment in segments:
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
                    
                    # Efek Pop-up: Membesar (130%) lalu normal (100%) dalam 0.1 detik
                    animated_text = f"{{\\fscx130\\fscy130\\t(0,100,\\fscx100\\fscy100)}}{text_content}"
                    f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{animated_text}\n")
        return ass_path

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
                '-loglevel', 'error',
                '-stats',
                '-i', video_path,
                '-vf', f"subtitles=filename='{clean_ass}':fontsdir='{clean_fonts}'",
                '-c:v', video_codec,
                '-preset', preset,
                '-crf', '20',
                '-c:a', 'copy',
                final_path
            ]
            subprocess.run(cmd, check=True)

        try:
            logging.info(f"Menggunakan folder font: {fonts_dir}")
            try:
                run_ffmpeg(use_gpu)
            except subprocess.CalledProcessError:
                if use_gpu:
                    logging.warning("⚠️ NVENC (GPU) gagal. Mencoba fallback ke CPU (libx264)...")
                    run_ffmpeg(False)
                else:
                    raise

            if os.path.exists(ass_path):
                os.remove(ass_path)
            logging.info(f"Sukses! Video disimpan di: {final_path}")
            return True
        except Exception as e:
            logging.error(f"Gagal burning subtitle: {e}")
            return False