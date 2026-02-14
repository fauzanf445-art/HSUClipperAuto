import os
import logging
import gc
from faster_whisper import WhisperModel, BatchedInferencePipeline
from pathlib import Path

# Import utilitas umum (get_video_resolution tidak lagi dibutuhkan di sini)
from yt_toolkit.core.utils import get_duration, setup_paths, print_progress

class VideoCaptioner:
    """
    Class untuk menghasilkan dan 'membakar' (burn-in) subtitle ke dalam video.
    Menggunakan faster-whisper untuk transkripsi AI dan FFmpeg untuk rendering video.
    """
    def __init__(self, model_size="large-v3-turbo", device="cpu", compute_type="int8", download_root=None):
        """
        Inisialisasi model Whisper.
        - model_size: Ukuran model yang akan digunakan (misal: "large-v3").
        - device: Perangkat untuk inferensi ('cuda' atau 'cpu').
        - compute_type: Tipe kuantisasi model ('float16', 'int8') untuk menghemat memori.
        - download_root: Folder untuk menyimpan file model AI.
        """
        if download_root is None:
            download_root = str(setup_paths().MODELS_DIR)
            
        if not os.path.exists(download_root):
            os.makedirs(download_root)

        self.device = device
        self.model = WhisperModel(
            model_size, 
            device=device, 
            compute_type=compute_type,
            local_files_only=False
        )

    @staticmethod
    def create_auto_device(model_size="large-v3-turbo", download_root=None):
        """
        Factory method untuk membuat instance VideoCaptioner dengan fallback otomatis.
        Mencoba: GPU (float16) -> GPU (int8) -> CPU (int8).
        """
        fallback_candidates = [
            ("cuda", "float16", "GPU High Precision"),
            ("cuda", "int8",    "GPU Low VRAM Mode"),
            ("cpu",  "int8",    "CPU")
        ]

        last_error = None
        for device, compute_type, desc in fallback_candidates:
            try:
                logging.info(f"Mencoba inisialisasi AI: {desc}...")
                instance = VideoCaptioner(model_size, device, compute_type, download_root)
                print(f"\r✅ AI Siap ({device.upper()} - {compute_type}).{' ' * 40}", flush=True)
                return instance
            except Exception as e:
                logging.warning(f"Gagal memuat AI ({desc}): {e}")
                last_error = e
                continue
        
        raise RuntimeError(f"Gagal memuat AI di semua perangkat. Error terakhir: {last_error}")

    def release(self):
        """Melepaskan model dari memori (VRAM/RAM) untuk mencegah OOM."""
        if hasattr(self, 'model'):
            del self.model
        # Paksa Garbage Collector untuk membersihkan sisa objek CTranslate2/Torch
        gc.collect()

    def _get_ass_style(self, w, h, alignment=2):
        """Mengatur tampilan teks adaptif berdasarkan resolusi layar."""
        # Logika styling adaptif: Ukuran font dan margin dihitung secara proporsional
        # terhadap tinggi video (h). Ini memastikan subtitle terlihat bagus di berbagai resolusi.
        font_size = int(h * 0.065)              # [REKOMENDASI] Sedikit lebih kecil agar 3 kata muat aman
        outline_size = int(font_size * 0.15)    # [REKOMENDASI] Outline tebal (Bold look) agar terbaca di background ramai
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
Style: Default,Poppins,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline_size},3,{alignment},10,10,{margin_v},1
"""

    def _format_timestamp_ass(self, seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02}:{secs:05.2f}"

    def generate_styled_ass(self, audio_source_path, target_w, target_h, alignment=2):
        """Transkripsi dengan gaya kata-per-kata dan highlight otomatis."""
        # Resolusi sekarang diterima dari parameter (sesuai target output processor)
        width, height = target_w, target_h

        total_duration = get_duration(audio_source_path)
        segments, _ = self.model.transcribe(audio_source_path, word_timestamps=True, vad_filter=True)
        
        # Simpan file .ass di lokasi yang sama dengan audio source
        ass_path = str(Path(audio_source_path).with_suffix(".ass"))
        header = self._get_ass_style(width, height, alignment)
        
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            for segment in segments:
                if total_duration > 0:
                    percent = int((segment.end / total_duration) * 100)
                    print_progress(percent, "Transkripsi")

                # --- LOGIKA ANIMASI KATA-PER-KATA ---
                words = segment.words
                # [MODIFIKASI] Mengambil per 3 kata agar lebih pas untuk format Shorts/Reels
                CHUNK_SIZE = 3
                for i in range(0, len(words), CHUNK_SIZE):
                    chunk = words[i:i + CHUNK_SIZE]
                    
                    # Loop internal untuk highlight berjalan (Karaoke Style)
                    # Kita buat event terpisah untuk setiap kata agar highlight berpindah
                    for j, active_word in enumerate(chunk):
                        start_sec = active_word.start
                        # Sambung ke kata berikutnya jika ada, agar teks tidak berkedip
                        end_sec = chunk[j+1].start if j < len(chunk) - 1 else active_word.end
                        
                        start = self._format_timestamp_ass(start_sec)
                        end = self._format_timestamp_ass(end_sec)
                        
                        text_parts = []
                        for w in chunk:
                            clean_word = w.word.strip().upper()
                            if w == active_word:
                                # [REKOMENDASI] Highlight Hijau Neon (&H0000FF00&) + Pop Lebih Besar (120%)
                                text_parts.append(f"{{\\1c&H0000FF00&\\fscx90\\fscy90\\t(0,50,\\fscx120\\fscy120)\\t(50,150,\\fscx100\\fscy100)}}{clean_word}")
                            else:
                                # Normal Putih + Reset Scale
                                text_parts.append(f"{{\\1c&HFFFFFF&\\fscx100\\fscy100}}{clean_word}")
                        
                        final_text = " ".join(text_parts)
                        f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{final_text}\n")
        
        # [GARBAGE COLLECTION] Hapus referensi segmen transkripsi yang berat
        del segments
        gc.collect()
        
        print(f"\r{' '*50}\r", end="") # Hapus baris progres
        return ass_path

    def transcribe_for_ai(self, audio_path):
        """Transkripsi audio mentah untuk keperluan summarization (fallback jika tidak ada CC)."""
        logging.info(f"Mulai transkripsi audio untuk summary: {audio_path}")

        total_duration = get_duration(audio_path)
        
        # Menggunakan Batched Pipeline untuk kecepatan ekstra pada audio panjang
        batched_model = BatchedInferencePipeline(model=self.model)
        
        # [AUTO-TUNE] Penyesuaian batch_size berdasarkan RAM tersedia untuk mencegah Crash
        batch_size = 4 # Default moderat
        try:
            import psutil
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024 ** 3)
            
            if available_gb < 4.0:
                logging.warning(f"⚠️ RAM Tersedia rendah ({available_gb:.2f} GB). Mengaktifkan Safe Mode (Batch Size 1).")
                batch_size = 1
            elif available_gb < 8.0:
                logging.info(f"ℹ️ RAM Tersedia sedang ({available_gb:.2f} GB). Mengurangi Batch Size ke 2.")
                batch_size = 2
            elif available_gb > 12.0:
                logging.info(f"🚀 RAM Melimpah ({available_gb:.2f} GB). Menggunakan High Performance Batch (16).")
                batch_size = 16
            else:
                batch_size = 8
        except ImportError:
            pass # psutil belum terinstal, gunakan default
            
        segments, _ = batched_model.transcribe(audio_path, beam_size=5, batch_size=batch_size)
        
        full_text = []
        print_progress(0, "Transkripsi Audio")
        
        for segment in segments:
            start = round(segment.start, 2)
            text = segment.text.strip()
            full_text.append(f"[{start}] {text}")
            
            if total_duration > 0:
                percent = int((segment.end / total_duration) * 100)
                print_progress(percent, "Transkripsi Audio")
            
        print(f"✅ Transkripsi: 100%      ")
        
        # [GARBAGE COLLECTION] Hapus model batch dan segmen
        del batched_model
        del segments
        gc.collect()
        
        return "\n".join(full_text)
