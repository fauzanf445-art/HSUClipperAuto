import os
import sys
# Matikan log C++ TensorFlow/MediaPipe (harus sebelum import library lain)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

import logging
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import shutil
from dotenv import load_dotenv

# Abaikan warning Python yang tidak kritikal
warnings.filterwarnings("ignore")

# Mengimpor modul dari package yt_toolkit
from yt_toolkit import Summarize, DownloadVidio, VideoProcessor, VideoCaptioner
from yt_toolkit.utils import update_cookies_from_browser, setup_paths, extract_video_id
from faster_whisper import available_models

def setup_logging():
    """
    Mengkonfigurasi logging terpusat untuk aplikasi.
    
    Fungsi ini melakukan hal berikut:
    1. Mengambil root logger.
    2. Menghapus semua handler yang ada untuk mencegah log duplikat yang mungkin 
       ditambahkan oleh modul lain (seperti dari package yt_toolkit).
    3. Mengatur File Handler (RotatingFileHandler) untuk menyimpan semua level log 
       (DEBUG ke atas) ke dalam 'debug.log'.
    4. Mengatur Console Handler (StreamHandler) untuk hanya menampilkan log level 
       WARNING ke atas, menjaga terminal tetap bersih.
    5. Mengatur level log untuk library pihak ketiga yang 'berisik' agar tidak 
       memenuhi file log.
       
    Ini memastikan bahwa `main.py` adalah satu-satunya sumber kebenaran untuk 
    konfigurasi logging di seluruh aplikasi, mengatasi potensi log ganda.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Hapus handler yang ada untuk mencegah duplikasi jika modul lain mengkonfigurasi logging.
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    # 1. File Handler: Menyimpan SEMUA log (DEBUG, INFO, ERROR) ke file 'debug.log'
    # Menggunakan RotatingFileHandler: Max 5MB per file, simpan hingga 3 file backup.
    log_dir = Path(".") # Simpan log di direktori yang sama dengan script/exe
    file_handler = RotatingFileHandler(log_dir / "debug.log", mode='a', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

    # 2. Console Handler: Hanya menampilkan WARNING & ERROR agar terminal tidak berantakan.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s')) # Tambahkan levelname untuk kejelasan
    root_logger.addHandler(console_handler)

    # Atur level library spesifik agar debug.log tidak penuh dengan request HTTP.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("absl").setLevel(logging.INFO) # absl bisa di INFO

def cleanup_on_exit(base_dir: Path, full_clean: bool = False):
    """
    Membersihkan cache, log, dan folder output internal project saat keluar.
    File yang sudah disalin ke folder Downloads user tidak akan terhapus.
    # PENTING: Fungsi ini memastikan tidak ada file sampah yang tertinggal setelah program ditutup.
    """
    print("\n👋 Menutup aplikasi...", end="", flush=True)
    
    # 1. Matikan Logging agar file log bisa dihapus (melepas lock file)
    logging.shutdown()
    
    if full_clean:
        print("\n🧹 Membersihkan cache & log...", end="", flush=True)
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

    print("\r✨ Sampai jumpa! 👋                     ")
    print("----------------------------------------")
    print("Big Thanks to:")
    print("- Video Engine: yt-dlp & FFmpeg")
    print("- AI Models   : MediaPipe (Face Tracking) & Faster-Whisper (ASR)")
    print("- Vision      : OpenCV")
    print("----------------------------------------")

def show_menu():
    """Menampilkan menu utama aplikasi."""
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
    print("5. Perbarui Cookies (Atasi Error 403)")
    print("   > Otomatis ambil cookies dari browser (Chrome/Edge/dll).")
    print("6. Refresh App (Hapus Cache)")
    print("   > Hapus file sementara dan folder output internal.")
    print("0. Keluar")

def main():
    
    # --- KONFIGURASI AWAL ---
    setup_logging() # Panggil fungsi konfigurasi logging terpusat

    print("\n" + "="*50)
    print("      YT TOOLKIT - AUTO CLIP & CAPTION")
    print("="*50)
    print("Memuat konfigurasi...", end="\n", flush=True)
    load_dotenv()

    # --- KONFIGURASI PATH TERPUSAT ---
    paths = setup_paths()

    WHISPER_MODEL = "large-v3-turbo"  # Opsi: "large-v3", "large-v3-turbo", "medium"
    DEVICE = "cuda"                  # Opsi: "cuda" jika ada GPU, "cpu" jika tidak
    
    # Validasi nama model
    if WHISPER_MODEL not in available_models() and "turbo" not in WHISPER_MODEL:
        logging.warning(f"⚠️ Model '{WHISPER_MODEL}' mungkin tidak valid. Model yang tersedia: {available_models()}")
    
    # --- VALIDASI API KEY ---
    # Coba load .env dari lokasi BASE_DIR (sebelah exe)
    env_path = paths.BASE_DIR / ".env"
    load_dotenv(dotenv_path=env_path)

    api_key = os.getenv('GEMINI_API_KEY')
    
    # Loop ini akan terus berjalan hingga API key yang valid tersedia.
    while True:
        # 1. Jika API Key ada (dari .env atau input sebelumnya), validasi dulu
        if api_key:
            print(f"⏳ Memvalidasi API Key...", end="\r", flush=True)
            if Summarize.validate_api_key(api_key):
                print(f"\r✅ API Key terkonfirmasi valid!{' '*30}", end="\r", flush=True)
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

    print(f"\r✅ Encoding menggunakan CPU.", end="\r", flush=True)
    
    # --- INISIALISASI MODEL AI (WHISPER) ---
    print(f"⏳ Menyiapkan AI Captioner ({WHISPER_MODEL})... ", end="", flush=True)

    # --- SISTEM FALLBACK BERTINGKAT (TIERED FALLBACK) ---
    # Strategi: Coba GPU High -> Coba GPU Low (Hemat VRAM) -> Coba CPU
    # Ini memastikan program tetap berjalan bahkan jika GPU tidak kuat atau tidak ada,
    # dengan otomatis memilih opsi terbaik yang tersedia.
    fallback_candidates = [
        ("cuda", "float16", "GPU High Precision (Cepat & Akurat)"),
        ("cuda", "int8",    "GPU Low VRAM Mode (Hemat Memori)"),
        ("cpu",  "int8",    "CPU (Lambat tapi Pasti)")
    ]

    captioner = None
    USE_AI_GPU = False # Flag ini akan menjadi True jika salah satu mode GPU berhasil.

    for device, compute_type, desc in fallback_candidates:
        try:
            captioner = VideoCaptioner(
                model_size=WHISPER_MODEL,
                device=device,
                compute_type=compute_type,
                download_root=str(paths.MODELS_DIR),
                ffmpeg_path=paths.FFMPEG_PATH,
                ffprobe_path=paths.FFPROBE_PATH
            )
            if device == "cuda":
                USE_AI_GPU = True
            print(f"\r✅ AI menggunakan {desc}.{' ' * 50}", flush=True)
            break # Berhenti looping jika berhasil
        except Exception as e:
            print(f"\r❌ Gagal memuat AI dengan mode '{desc}'. Mencoba mode berikutnya{' '*20}", end="\r", flush=True)
            continue

    if captioner is None:
        logging.critical("Gagal memuat AI Captioner di semua perangkat (GPU/CPU). Program berhenti.")
        return

    # 🔄 LOOP UTAMA PROGRAM
    while True:
        # --- DETEKSI COOKIE OTOMATIS (SETIAP LOOP) ---
        # Mencari file cookie yang paling baru diubah di folder 'cookies'.
        # Ini memastikan jika pengguna baru saja memperbarui cookie, file terbaru akan digunakan.
        active_cookie_path = None
        COOKIES_DIR = paths.BASE_DIR / "cookies"
        COOKIES_DIR.mkdir(exist_ok=True) # Pastikan folder ada sebelum diakses
        try:
            # Cari semua file .txt di dalam folder cookies
            cookie_files = list(COOKIES_DIR.glob("*.txt"))
            if cookie_files:
                # Temukan file dengan waktu modifikasi terbaru
                latest_cookie_file = max(cookie_files, key=os.path.getmtime)
                active_cookie_path = str(latest_cookie_file)
                print(f"\r✅ Cookie aktif: {latest_cookie_file.name} (paling baru){' '*20}")
            else:
                logging.warning(f"⚠️ File cookie tidak ditemukan. Untuk mengatasi error 403, gunakan menu 5.")
        except Exception as e:
            logging.error(f"Gagal mencari file cookie: {e}", exc_info=True)

        show_menu()
        
        choice = input("\nPilihan Anda (0-5):").strip()
        
        if choice == "0":
            cleanup_on_exit(paths.BASE_DIR, full_clean=False)
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

        if choice == "5":
            print("\n--- PERBARUI COOKIES OTOMATIS ---")
            print("Pilih browser yang Anda gunakan untuk login YouTube:")
            print("1. Google Chrome")
            print("2. Microsoft Edge")
            print("3. Firefox")
            print("4. Opera")
            print("5. Brave")
            
            b_choice = input("Pilih browser (1-5): ").strip()
            browser_map = {
                "1": "chrome",
                "2": "edge",
                "3": "firefox",
                "4": "opera",
                "5": "brave"
            }
            
            selected_browser = browser_map.get(b_choice)
            if selected_browser:
                print(f"\n⚠️  PENTING: Mohon TUTUP browser {selected_browser} agar proses berhasil.")
                input("Tekan Enter jika browser sudah ditutup...")
                target_cookie_file = COOKIES_DIR / f"{selected_browser}_cookies.txt"
                update_cookies_from_browser(selected_browser, str(target_cookie_file))
            else:
                print("❌ Pilihan browser tidak valid.")
            continue

        if choice == "6":
            cleanup_on_exit(paths.BASE_DIR, full_clean=True)
            # Re-setup logging karena shutdown dipanggil di cleanup
            setup_logging()
            print(f"\r✅ Cache berhasil dihapus! Sistem bersih.{' '*30}")
            
            input("\nTekan Enter untuk kembali ke menu...")
            continue

        if choice not in ["1", "2", "3", "4", "5", "6"]:
            print("❌ Pilihan tidak valid.")
            continue
        
        url = input("Masukkan URL YouTube: ").strip()
        if not url:
            print("❌ URL tidak boleh kosong.")
            continue

        try:
            # --- 1. UNDUH ASET & ANALISIS KONTEN ---
            print("\n[1/5] Mengunduh Aset & Menganalisa Video...")
            downloader = DownloadVidio(
                url=url, 
                output_dir=str(paths.RAW_ASSETS_DIR),
                ffmpeg_path=paths.FFMPEG_PATH,
                ffprobe_path=paths.FFPROBE_PATH,
                deno_path=paths.DENO_PATH,
                use_gpu=False, # FFmpeg dipaksa CPU
                cookies_path=active_cookie_path
            )
            
            # --- LOGIKA RESUME ---
            # Cek apakah folder untuk video ini sudah ada untuk melanjutkan proses sebelumnya.
            video_id = extract_video_id(url)
            existing_folder = None
            if video_id and paths.RAW_ASSETS_DIR.exists():
                for path in paths.RAW_ASSETS_DIR.iterdir():
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

            # Jika file master dan JSON sudah ada, lewati proses download dan analisis.
            if master_mkv_path.exists() and json_path.exists():
                 print("⏩ Aset lengkap (Master Video & JSON). Melewati unduhan.")
            else:
                # download video + audio
                v_path, a_path = downloader.download_both_separate()
                
                if not v_path or not a_path:
                    print("❌ Gagal mendapatkan file video/audio. Cek koneksi atau URL.")
                    continue
            
            # Jika file JSON sudah ada, lewati analisis Gemini yang memakan waktu dan biaya.
            if json_path.exists():
                print(f"⏩ [1/5] File analisis ditemukan: {json_path.name}. Melewati analisis AI.")
            else:
                # Konversi audio khusus untuk AI (MP3) agar upload Gemini stabil
                ai_audio_path = downloader.convert_audio_for_ai(a_path)
                if not ai_audio_path:
                    print("❌ Gagal konversi audio untuk AI.")
                    continue

                # Mendapatkan transkrip dan klip terbaik via Gemini
                summarizer = Summarize(api_key=api_key, out_dir=str(paths.RAW_ASSETS_DIR), ffmpeg_path=paths.FFMPEG_PATH, ffprobe_path=paths.FFPROBE_PATH, cookies_path=active_cookie_path)
                transcript = summarizer.get_transcript(url, audio_path=ai_audio_path, captioner=captioner)

                # jalankan summarization
                summary = summarizer.generate_summarize(transcript, url, ai_audio_path)
                
                # simpan ringkasan + transkrip ke JSON
                json_path = Path(summarizer.save_summary(url, summary, transcript, target_dir=downloader.raw_dir))

            print(f"\r✅ [1/5] Mengunduh aset dan analisa selesai!{' ' * 50}\n", end="\n", flush=True)

            # --- 2. REMUXING (STANDARISASI VIDEO) ---
            if master_mkv_path.exists():
                print(f"⏩ [2/5] File Master ditemukan: {master_mkv_path.name}. Melewati Remux.")
            else:
                print("[2/5] Menggabungkan Video & Audio (Remux)...")
                downloader.remux_video_audio(v_path, a_path)
                print(f"\r✅ [2/5] Remuxing selesai!{' ' * 50}\n", end="\r", flush=True)

            # --- 3. PEMOTONGAN KLIP ---
            print("[3/5] Memotong Klip Mentah (MKV)...")
            # Pastikan kirim string path ke fungsi yang mengharapkan string
            raw_clips = downloader.create_raw_clips(str(json_path))
            print(f"\r✅ [3/5] Pemotongan klip selesai!{' ' * 50}\n", end="\r", flush=True)
            
            if not raw_clips:
                print("❌ Tidak ada klip yang berhasil dipotong.")
                continue

            # KONSISTENSI: Jangan susun ulang path manual, gunakan path dari downloader
            input_dir = video_raw_path / "raw_clip_landscape"
            output_dir_portrait = video_raw_path / "raw_clip_portrait"
            output_dir_portrait.mkdir(parents=True, exist_ok=True)
            
            # Menyiapkan folder output final yang terpisah agar Raw Assets tetap bersih
            video_final_dir = paths.FINAL_OUTPUT_DIR / downloader.asset_folder_name
            video_final_dir.mkdir(parents=True, exist_ok=True)

            # --- 4. PEMROSESAN VISUAL (REFORMAT KE 9:16) ---
            processed_clips = []

            if choice == "1": # Monologue Mode (AI Face Tracking)
                print(f"[4/5] Menjalankan Monologue Mode (AI Face Tracking)...")
                # Mengambil file dari input_dir dan mengurutkannya
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))

                for i, clip_path in enumerate(raw_clip_files):
                    # Inisialisasi Processor DI DALAM loop untuk setiap klip (Reset State).
                    proc = VideoProcessor(model_path=str(paths.DETECTOR_MODEL_PATH), ffmpeg_path=paths.FFMPEG_PATH, ffprobe_path=paths.FFPROBE_PATH, use_gpu=USE_AI_GPU)
                    try:
                        out_name = f"portrait_{clip_path.stem}.mkv"
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Portrait ({i+1}/{len(raw_clip_files)}): {clip_path.name[:30]}...{' '*30}", end='', flush=True)
                        if proc.process_portrait(str(clip_path.resolve()), str(output_file)):
                            processed_clips.append(output_file)
                        else:
                            logging.error(f"Gagal memproses klip (Monologue): {clip_path.name}")
                    finally:
                        proc.close()
                print(f"\r✅ [4/5] Proses Portrait selesai!{' ' * 50}\n", end="\r", flush=True)
            
            elif choice == "2": # Podcast Mode
                print(f"[4/5] Menjalankan Podcast Mode (Smart Static)...")
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                for i, clip_path in enumerate(raw_clip_files):
                    proc = VideoProcessor(model_path=str(paths.DETECTOR_MODEL_PATH), ffmpeg_path=paths.FFMPEG_PATH, ffprobe_path=paths.FFPROBE_PATH, use_gpu=USE_AI_GPU)
                    try:
                        out_name = f"podcast_{clip_path.stem}.mkv"
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Podcast ({i+1}/{len(raw_clip_files)}): {clip_path.name[:30]}...{' '*30}", end='', flush=True)
                        if proc.process_podcast_portrait(str(clip_path.resolve()), str(output_file)):
                            processed_clips.append(output_file)
                        else:
                            logging.error(f"Gagal memproses klip (Podcast): {clip_path.name}")
                    finally:
                        proc.close()
                print(f"\r✅ [4/5] Proses Podcast selesai!{' ' * 50}\n", end="\r", flush=True)

            else: # Choice == 3 (Cinematic Mode)
                print(f"[4/5] Menjalankan Cinematic Mode (Vlog/Doc)...")
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                for i, clip_path in enumerate(raw_clip_files):
                    proc = VideoProcessor(model_path=str(paths.DETECTOR_MODEL_PATH), ffmpeg_path=paths.FFMPEG_PATH, ffprobe_path=paths.FFPROBE_PATH, use_gpu=USE_AI_GPU)
                    try:
                        out_name = f"cinematic_{clip_path.stem}.mkv"
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"\r⏳ Memproses Cinematic ({i+1}/{len(raw_clip_files)}): {clip_path.name[:30]}...{' '*30}", end='', flush=True)
                        if proc.process_cinematic_portrait(str(clip_path.resolve()), str(output_file)):
                            processed_clips.append(output_file)
                        else:
                            logging.error(f"Gagal memproses klip (Cinematic): {clip_path.name}")
                    finally:
                        proc.close()
                print(f"\r✅ [4/5] Proses Cinematic selesai!{' ' * 50}\n", end="\r", flush=True)

            # --- 5. PENAMBAHAN CAPTION (SUBTITLE) ---
            print(f"[5/5] Menghasilkan Caption dengan {WHISPER_MODEL}...")
            for i, clip in enumerate(processed_clips):
                # Tentukan nama file akhir (misal: portrait_clip_1_final.mkv)
                final_output = (video_final_dir / f"{clip.stem}_final.mkv").resolve()
                
                if final_output.exists():
                    continue
                
                print(f"\r⏳ Menambahkan Caption ({i+1}/{len(processed_clips)}): {clip.name[:30]}...{' '*30}", end='', flush=True)
                # Kirim path absolut ke captioner
                captioner.process_full_caption(
                    video_path=str(clip), 
                    final_path=str(final_output),
                    fonts_dir=str(paths.FONTS_DIR),
                    use_gpu=False # FFmpeg dipaksa CPU
                )

            print(f"\r✅ [5/5] Penambahan caption selesai!{' ' * 50}\n", end="\r", flush=True)

            # --- 6. SALIN HASIL AKHIR ---
            try:
                print(f"Finishing Step: Menyalin output ke folder Downloads...", end="\r", flush=True)
                downloads_path = Path.home() / "Downloads"
                dest_dir = downloads_path / video_final_dir.name
                
                shutil.copytree(video_final_dir, dest_dir, dirs_exist_ok=True)
                print(f"📂 Folder tersalin di: {dest_dir}", end="\n")

                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_OK) # Bunyi 'Ding' standar Windows
                except ImportError:
                    print('\a') # Fallback beep sederhana
            except Exception as e:
                # Tampilkan pesan error sederhana ke user, tapi log detail lengkapnya untuk debug
                print(f"⚠️ Gagal menyalin hasil akhir ke folder Downloads: {e}")
                logging.warning(f"Gagal menyalin {video_final_dir} ke Downloads.", exc_info=True)

        except Exception as e:
            # Menangkap semua error yang tidak terduga selama proses dan mencatatnya.
            logging.critical(f"Terjadi kesalahan fatal di loop utama: {e}", exc_info=True)
            input("\nTekan Enter untuk kembali ke menu...")

if __name__ == "__main__":
    main()