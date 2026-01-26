import os
import sys
# [CLEANUP] Matikan log C++ TensorFlow/MediaPipe (harus sebelum import library lain)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

import logging
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import shutil
from dotenv import load_dotenv

# [CLEANUP] Abaikan warning Python yang tidak kritikal
warnings.filterwarnings("ignore")

# Mengimpor modul dari package yt_toolkit
from yt_toolkit import Summarize, DownloadVidio, VideoProcessor, VideoCaptioner
from faster_whisper import available_models


# --- KONFIGURASI LOGGING (Dual Handler) ---
# 1. File Handler: Menyimpan SEMUA log (Debug/Info/Error) ke file 'debug.log'
# Menggunakan RotatingFileHandler: Max 5MB per file, simpan hingga 3 file backup
file_handler = RotatingFileHandler("debug.log", mode='a', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# 2. Console Handler: Hanya menampilkan WARNING/ERROR agar terminal tetap bersih
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('%(message)s'))

# Terapkan konfigurasi
logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])

# Atur level library spesifik agar debug.log tidak penuh dengan sampah HTTP request
logging.getLogger("urllib3").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("huggingface_hub").setLevel(logging.INFO)
logging.getLogger("absl").setLevel(logging.INFO)

def check_nvenc_support(ffmpeg_path: str) -> bool:
    """
    Memeriksa apakah FFmpeg mendukung NVENC dengan melakukan tes encoding nyata.
    Hanya mengecek daftar encoder tidak cukup karena bisa error saat runtime (masalah driver).
    """
    try:
        # Perintah dummy: encode video hitam 1 detik ke null output
        # Jika driver bermasalah (cuMemAllocAsync), perintah ini akan error
        cmd = [
            ffmpeg_path, '-hide_banner', '-y',
            '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=30',
            '-c:v', 'h264_nvenc', '-preset', 'p4',
            '-t', '1',
            '-f', 'null', '-'
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def cleanup_on_exit(base_dir: Path):
    """
    Membersihkan cache, log, dan folder output internal project saat keluar.
    File yang sudah disalin ke folder Downloads user tidak akan terhapus.
    """
    print("\n🧹 Membersihkan sistem...", end="", flush=True)
    
    # 1. Matikan Logging agar file log bisa dihapus (melepas lock file)
    logging.shutdown()
    
    # Hapus debug.log dan backup-nya (debug.log.1, dst)
    for log_file in base_dir.glob("debug.log*"):
        try:
            os.remove(log_file)
        except Exception:
            pass
            
    # 2. Hapus Folder Output Internal (Raw Assets & Final Output Project)
    output_dir = base_dir / "output"
    if output_dir.exists():
        try:
            shutil.rmtree(output_dir)
        except Exception:
            pass

    print("\r✨ Sistem bersih. Sampai jumpa! 👋       ")

def main():
    
    print("\n" + "="*50)
    print("      YT TOOLKIT - AUTO CLIP & CAPTION")
    print("="*50)
    print("Memuat konfigurasi...", end="\n", flush=True)
    load_dotenv()
    WHISPER_MODEL = "large-v3-turbo"  # Opsi: "large-v3", "large-v3-turbo", "medium"
    DEVICE = "cuda"                  # Opsi: "cuda" jika ada GPU, "cpu" jika tidak
    
    # Validasi nama model
    if WHISPER_MODEL not in available_models() and "turbo" not in WHISPER_MODEL:
        logging.warning(f"⚠️ Model '{WHISPER_MODEL}' mungkin tidak valid. Model yang tersedia: {available_models()}")

    # --- KONFIGURASI ---
    # konfigurasi direktori dasar(root)
    # Deteksi apakah berjalan sebagai script python biasa atau exe (frozen)
    if getattr(sys, 'frozen', False):
        BASE_DIR = Path(sys.executable).parent
    else:
        BASE_DIR = Path(__file__).parent.resolve()

    OUTPUT_DIR = BASE_DIR / "output"
    RAW_ASSETS_DIR = OUTPUT_DIR / "raw_assets"
    RAW_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_OUTPUT_DIR = OUTPUT_DIR / "final_output"

    # konfigurasi fonts dan models
    FONTS_DIR = BASE_DIR / "fonts"
    MODELS_DIR = BASE_DIR / "models"
    DETECTOR_MODEL_PATH = MODELS_DIR / "detector.tflite"

    # Validasi Path: Memastikan folder fonts dan file model benar-benar ada
    if not FONTS_DIR.exists():
        logging.warning(f"⚠️ Folder fonts tidak ditemukan di: {FONTS_DIR}. Pastikan Anda sudah membuatnya.")
    if not DETECTOR_MODEL_PATH.exists():
        logging.warning(f"⚠️ Model detector tidak ditemukan di: {DETECTOR_MODEL_PATH}. Harap pindahkan 'detector.tflite' ke dalam folder 'models'.")

    # Konfigurasi Tools (FFmpeg & Deno)
    BIN_DIR = BASE_DIR / "bin"
    if not BIN_DIR.exists():
        logging.warning(f"⚠️ Folder 'bin' tidak ditemukan. Disarankan membuat folder 'bin' dan memindahkan ffmpeg/deno ke sana agar rapi.")

    FFMPEG_BIN = BIN_DIR / "ffmpeg.exe"
    FFMPEG_PATH = str(FFMPEG_BIN) if FFMPEG_BIN.exists() else "ffmpeg"

    FFPROBE_BIN = BIN_DIR / "ffprobe.exe"
    FFPROBE_PATH = str(FFPROBE_BIN) if FFPROBE_BIN.exists() else "ffprobe"

    DENO_BIN = BIN_DIR / "deno.exe"
    DENO_PATH = str(DENO_BIN) if DENO_BIN.exists() else "deno"

    # --- LOGIKA API KEY DINAMIS ---
    # Coba load .env dari lokasi BASE_DIR (sebelah exe)
    env_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key = os.getenv('GEMINI_API_KEY')
    
    while True:
        # 1. Jika API Key ada (dari .env atau input sebelumnya), validasi dulu
        if api_key:
            print(f"⏳ Memvalidasi API Key...", end="\r", flush=True)
            if Summarize.validate_api_key(api_key):
                print(f"✅ API Key terkonfirmasi valid!{' '*30}")
                os.environ['GEMINI_API_KEY'] = api_key
                break # Keluar dari loop, lanjut ke program utama
            else:
                print(f"❌ API Key tidak valid atau kadaluarsa.{' '*30}")
                api_key = None # Reset agar masuk ke mode input
        
        # 2. Jika tidak ada key atau invalid, minta input user
        print(f"\n⚠️  Konfigurasi API Key Diperlukan ({env_path})")
        print("   Dapatkan key di: https://aistudio.google.com/app/apikey")
        user_input_key = input("👉 Masukkan Gemini API Key: ").strip()
        
        if not user_input_key:
            print("❌ API Key wajib diisi. Program berhenti.")
            return

        # 3. Cek input user sebelum disimpan
        print(f"⏳ Memeriksa kunci...", end="\r", flush=True)
        if Summarize.validate_api_key(user_input_key):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f'GEMINI_API_KEY="{user_input_key}"\n')
            print(f"✅ File .env berhasil diperbarui!{' '*30}")
            api_key = user_input_key # Set variabel agar lolos validasi di awal loop berikutnya
        else:
            print(f"❌ API Key yang Anda masukkan salah. Silakan coba lagi.{' '*20}")

    # --- DETEKSI PERANGKAT KERAS ---
    # 1. Periksa dukungan NVENC untuk encoding video
    USE_NVENC_FOR_ENCODING = check_nvenc_support(FFMPEG_PATH)
    if USE_NVENC_FOR_ENCODING:
        print(f"✅ Menggunakan GPU.")
    else:
        print(f"✅ Menggunakan CPU")
    
    print(f"⏳ Menyiapkan AI Captioner ({WHISPER_MODEL})... ", end="", flush=True)

    # --- SISTEM FALLBACK BERTINGKAT (TIERED FALLBACK) ---
    # Strategi: Coba GPU High -> Coba GPU Low (Hemat VRAM) -> Coba CPU
    fallback_candidates = [
        ("cuda", "float16", "GPU High Precision (Cepat & Akurat)"),
        ("cuda", "int8",    "GPU Low VRAM Mode (Hemat Memori)"),
        ("cpu",  "int8",    "CPU (Lambat tapi Pasti)")
    ]

    captioner = None
    USE_AI_GPU = False # Flag ini KHUSUS untuk AI (Whisper & MediaPipe)

    for device, compute_type, desc in fallback_candidates:
        try:
            captioner = VideoCaptioner(
                model_size=WHISPER_MODEL,
                device=device,
                compute_type=compute_type,
                download_root=str(MODELS_DIR),
                ffmpeg_path=FFMPEG_PATH,
                ffprobe_path=FFPROBE_PATH
            )
            if device == "cuda":
                USE_AI_GPU = True
            print(f"\r✅ AI menggunakan {desc}.{' ' * 50}", flush=True)
            break # Berhenti looping jika berhasil
        except Exception:
            continue

    if captioner is None:
        print(f"❌ Gagal memuat AI di semua perangkat. Program berhenti.")
        return

    # 🔄 LOOP UTAMA PROGRAM
    while True:
        print("="*50)
        print("      MENU PILIHAN TIPE PROJECT")
        print("="*50)
        print("1. Monologue Mode (AI Face Tracking 9:16)")
        print("   > Untuk video monolog. Kamera mengikuti wajah pembicara.")
        print("2. Podcast Mode (Smart Static 9:16)")
        print("   > Untuk podcast 2 orang. Kamera auto-cut bergantian.")
        print("3. Cinematic Mode (Vlog/Doc 9:16)")
        print("   > Untuk vlog atau dokumentasi. Video di tengah + background blur.")
        print("4. Ganti API Key")
        print("   > Ganti kunci API Gemini jika limit habis atau error.")
        print("0. Keluar")
        
        choice = input("\nPilih tipe project: ").strip()
        
        if choice == "0":
            cleanup_on_exit(BASE_DIR)
            break
            
        if choice == "4":
            print("\n--- GANTI API KEY ---")
            print(f"Key saat ini: {api_key[:5]}...{api_key[-5:] if api_key else 'None'}")
            new_key = input("👉 Masukkan Gemini API Key baru: ").strip()
            
            if not new_key:
                print("⚠️ Input kosong. Kembali ke menu utama.")
                continue

            print(f"⏳ Memvalidasi API Key baru...", end="\r", flush=True)
            if Summarize.validate_api_key(new_key):
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f'GEMINI_API_KEY="{new_key}"\n')
                os.environ['GEMINI_API_KEY'] = new_key
                api_key = new_key
                print(f"✅ API Key berhasil diperbarui dan disimpan!{' '*30}")
            else:
                print(f"❌ API Key tidak valid. Perubahan dibatalkan.{' '*30}")
            continue

        if choice not in ["1", "2", "3"]:
            print("❌ Pilihan tidak valid.")
            continue
        
        url = input("Masukkan URL YouTube: ").strip()
        if not url:
            print("❌ URL tidak boleh kosong.")
            continue

        try:
            # --- [STEP 1] DOWNLOAD & SUMMARIZE ---
            print("\n[Step 1/5] Mengunduh Aset & Menganalisa Video...")
            downloader = DownloadVidio(
                url=url, 
                output_dir=str(RAW_ASSETS_DIR),
                ffmpeg_path=FFMPEG_PATH,
                ffprobe_path=FFPROBE_PATH,
                deno_path=DENO_PATH,
                use_gpu=USE_NVENC_FOR_ENCODING, # Gunakan flag NVENC untuk download/remux
                resolution="1080"
            )
            
            # [OPTIMISASI] Cek folder eksisting untuk skip fetch metadata
            video_id = DownloadVidio.extract_video_id(url)
            existing_folder = None
            if video_id and RAW_ASSETS_DIR.exists():
                for path in RAW_ASSETS_DIR.iterdir():
                    if path.is_dir() and path.name.endswith(f"-{video_id}"):
                        existing_folder = path
                        break
            
            if existing_folder:
                print(f"⏩ Folder aset ditemukan: {existing_folder.name}")
                downloader.asset_folder_name = existing_folder.name
                downloader.raw_dir = str(existing_folder)
                downloader.video_title = existing_folder.name 
            else:
                # Ambil metadata dan siapkan folder berdasarkan judul video
                downloader.setup_directories()

            # Path referensi
            video_raw_path = Path(downloader.raw_dir)
            master_mkv_path = video_raw_path / 'master.mkv'
            json_path = video_raw_path / 'transcripts.json'
            
            v_path, a_path = None, None

            # Cek kelengkapan aset untuk skip download
            if master_mkv_path.exists() and json_path.exists():
                 print("⏩ Aset lengkap (Master Video & JSON). Melewati unduhan.")
            else:
                # download video + audio
                v_path, a_path = downloader.download_both_separate()
                
                if not v_path or not a_path:
                    print("❌ Gagal mendapatkan file video/audio. Cek koneksi atau URL.")
                    continue
            
            # Cek apakah file JSON sudah ada (Skip Analisis AI jika resume)
            if json_path.exists():
                print(f"⏩ [Step 1] File analisis ditemukan: {json_path.name}. Melewati analisis AI.")
            else:
                # Konversi audio khusus untuk AI (MP3) agar upload Gemini stabil
                ai_audio_path = downloader.convert_audio_for_ai(a_path)
                if not ai_audio_path:
                    print("❌ Gagal konversi audio untuk AI.")
                    continue

                # Mendapatkan transkrip dan klip terbaik via Gemini
                summarizer = Summarize(api_key=api_key, out_dir=str(RAW_ASSETS_DIR), ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH)
                transcript = summarizer.get_transcript(url, audio_path=ai_audio_path, captioner=captioner)

                # jalankan summarization
                summary = summarizer.generate_summarize(transcript, url, ai_audio_path)
                
                # simpan ringkasan + transkrip ke JSON
                json_path = Path(summarizer.save_summary(url, summary, transcript, target_dir=downloader.raw_dir))

            # [CLEANUP] Pesan final Step 1 yang bersih
            print(f"\r✅ [Step 1] Mengunduh aset dan analisa selesai!{' ' * 50}\n", end="", flush=True)

            # --- [STEP 2] REMUXING ---
            if master_mkv_path.exists():
                print(f"⏩ [Step 2] File Master ditemukan: {master_mkv_path.name}. Melewati Remux.")
            else:
                print("[Step 2/5] Menggabungkan Video & Audio (Remux)...")
                downloader.remux_video_audio(v_path, a_path)
                print(f"\r✅ [Step 2] Remuxing selesai!{' ' * 50}", end="\n", flush=True)

            # --- [STEP 3] CLIPPING ---
            print("[Step 3/5] Memotong Klip Mentah (MKV)...")
            # Pastikan kirim string path ke fungsi yang mengharapkan string
            raw_clips = downloader.create_raw_clips(str(json_path))
            print(f"\r✅ [Step 3] Pemotongan klip selesai!{' ' * 50}", end="\n", flush=True)
            
            if not raw_clips:
                print("❌ Tidak ada klip yang berhasil dipotong.")
                continue

            # KONSISTENSI: Jangan susun ulang path manual, gunakan path dari downloader
            input_dir = video_raw_path / "raw_clip_landscape"
            output_dir_portrait = video_raw_path / "raw_clip_portrait"
            output_dir_portrait.mkdir(parents=True, exist_ok=True)
            
            # Menyiapkan folder output final yang terpisah agar Raw Assets tetap bersih
            video_final_dir = FINAL_OUTPUT_DIR / downloader.asset_folder_name
            video_final_dir.mkdir(parents=True, exist_ok=True)

            # --- [STEP 4] VISUAL PROCESSING ---
            processed_clips = []

            if choice == "1": # Monologue Mode (AI Face Tracking)
                print(f"[Step 4/5] Menjalankan Monologue Mode (AI Face Tracking)...")
                # Mengambil file dari input_dir dan mengurutkannya
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                # Inisialisasi Processor di luar loop agar model hanya dimuat sekali (Hemat Resource)
                proc = VideoProcessor(model_path=str(DETECTOR_MODEL_PATH), ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH, use_gpu=USE_AI_GPU) # MediaPipe menggunakan flag AI
                try:
                    for i, clip_path in enumerate(raw_clip_files):
                        out_name = f"portrait_{clip_path.stem}.mkv"
                        # Gunakan .resolve() untuk menghindari error 'Invalid argument' di Windows
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Portrait ({i+1}/{len(raw_clip_files)}): {clip_path.name}...", end='', flush=True)
                         # Kirim path sebagai string absolut
                        proc.process_portrait(str(clip_path.resolve()), str(output_file))
                        processed_clips.append(output_file)
                finally:
                    proc.close()
                print(f"\r✅ [Step 4] Proses Portrait selesai!{' ' * 50}", end="\n", flush=True)
            
            elif choice == "2": # Podcast Mode
                print(f"[Step 4/5] Menjalankan Podcast Mode (Smart Static)...")
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                # Inisialisasi Processor (Butuh GPU/CPU untuk deteksi wajah)
                proc = VideoProcessor(model_path=str(DETECTOR_MODEL_PATH), ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH, use_gpu=USE_AI_GPU)
                try:
                    for i, clip_path in enumerate(raw_clip_files):
                        out_name = f"podcast_{clip_path.stem}.mkv"
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Podcast ({i+1}/{len(raw_clip_files)}): {clip_path.name}...", end='', flush=True)
                        proc.process_podcast_portrait(str(clip_path.resolve()), str(output_file))
                        processed_clips.append(output_file)
                finally:
                    proc.close()
                print(f"\r✅ [Step 4] Proses Podcast selesai!{' ' * 50}", end="\n", flush=True)

            else: # Choice == 3 (Cinematic Mode)
                print(f"[Step 4/5] Menjalankan Cinematic Mode (Vlog/Doc)...")
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                # Inisialisasi Processor
                proc = VideoProcessor(model_path=str(DETECTOR_MODEL_PATH), ffmpeg_path=FFMPEG_PATH, ffprobe_path=FFPROBE_PATH, use_gpu=USE_AI_GPU)
                try:
                    for i, clip_path in enumerate(raw_clip_files):
                        out_name = f"cinematic_{clip_path.stem}.mkv"
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Cinematic ({i+1}/{len(raw_clip_files)}): {clip_path.name}...", end='', flush=True)
                        proc.process_cinematic_portrait(str(clip_path.resolve()), str(output_file))
                        processed_clips.append(output_file)
                finally:
                    proc.close()
                print(f"\r✅ [Step 4] Proses Cinematic selesai!{' ' * 50}", end="\n", flush=True)

            # --- [STEP 5] AI CAPTIONING ---
            print(f"[Step 5/5] Menghasilkan Caption dengan {WHISPER_MODEL}...")
            for i, clip in enumerate(processed_clips):
                # Tentukan nama file akhir (misal: portrait_clip_1_final.mkv)
                final_output = (video_final_dir / f"{clip.stem}_final.mkv").resolve()
                
                if final_output.exists():
                    continue
                
                print(f"\r⏳ Menambahkan Caption ({i+1}/{len(processed_clips)}): {clip.name}...", end='', flush=True)
                # Kirim path absolut ke captioner
                captioner.process_full_caption(
                    video_path=str(clip), 
                    final_path=str(final_output),
                    fonts_dir=str(FONTS_DIR),
                    use_gpu=USE_NVENC_FOR_ENCODING # Burn-in subtitle menggunakan flag NVENC
                )

            print(f"\r✅ [Step 5] Penambahan caption selesai!{' ' * 50}", end="\n", flush=True)
            print(f"\n🎉 SUKSES! Semua file tersedia di: {video_final_dir}")

            # --- [STEP 6] COPY TO DOWNLOADS ---
            try:
                print(f"FInishing Step: Menyalin output ke folder Downloads...")
                downloads_path = Path.home() / "Downloads"
                dest_dir = downloads_path / video_final_dir.name
                
                shutil.copytree(video_final_dir, dest_dir, dirs_exist_ok=True)
                print(f"📂 Folder tersalin di: {dest_dir}")

                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_OK) # Bunyi 'Ding' standar Windows
                except ImportError:
                    print('\a') # Fallback beep sederhana
            except Exception as e:
                print(f"⚠️ Gagal menyalin ke Downloads: {e}")

        except Exception as e:
            print(f"\n❌ Terjadi kesalahan pada loop ini: {e}")
            input("\nTekan Enter untuk kembali ke menu...")

if __name__ == "__main__":
    main()