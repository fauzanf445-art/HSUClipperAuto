import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Mengimpor modul dari package yt_toolkit
from yt_toolkit import Summarize, DownloadVidio, VideoProcessor, VideoCaptioner


# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    load_dotenv()
    WHISPER_MODEL = "large-v3-turbo"  # Opsi: "large-v3", "large-v3-turbo", "medium"
    DEVICE = "cuda"                  # Opsi: "cuda" jika ada GPU, "cpu" jika tidak
    COMPUTE_TYPE = "float16"         # Opsi: "float16" (GPU), "int8" (CPU)    
    USE_GPU = DEVICE == "cuda"       # Boolean untuk kontrol FFmpeg (NVENC vs libx264)
    
    # --- KONFIGURASI ---
    # konfigurasi direktori dasar(root)
    BASE_DIR = Path(__file__).parent.resolve()
    OUTPUT_DIR = BASE_DIR / "output"
    RAW_ASSETS_DIR = OUTPUT_DIR / "raw_assets"
    FINAL_OUTPUT_DIR = OUTPUT_DIR / "final_output"

    # konfigurasi fonts dan models
    FONTS_DIR = BASE_DIR / "fonts"
    MODELS_DIR = BASE_DIR / "models"
    DETECTOR_MODEL_PATH = BASE_DIR / "detector.tflite"

    # Konfigurasi Tools (FFmpeg & Deno)
    FFMPEG_BIN = BASE_DIR / "ffmpeg.exe"
    FFMPEG_PATH = str(FFMPEG_BIN) if FFMPEG_BIN.exists() else "ffmpeg"

    FFPROBE_BIN = BASE_DIR / "ffprobe.exe"
    FFPROBE_PATH = str(FFPROBE_BIN) if FFPROBE_BIN.exists() else "ffprobe"

    DENO_BIN = BASE_DIR / "deno.exe"
    DENO_PATH = str(DENO_BIN) if DENO_BIN.exists() else "deno"

    api_key = os.getenv('GEMINI_API_KEY')
    hf_token = os.getenv('HF_TOKEN')
    
    
    if api_key:
        os.environ['GEMINI_API_KEY'] = api_key
        logging.info("✅ GEMINI_API_KEY terkonfirmasi.")
    else:
        logging.error("❌ GEMINI_API_KEY tidak ditemukan di .env. Silakan tambahkan kunci API Anda.")
        return
    
    if hf_token:
        os.environ['HF_TOKEN'] = hf_token
        logging.info("✅ HF_TOKEN terkonfirmasi.")
    else:
        logging.error("❌ HF_TOKEN tidak ditemukan di .env. Silakan tambahkan token Hugging Face Anda.")
        return
    
    print("\n" + "-"*30)
    print(f"⏳ Menyiapkan AI Captioner ({WHISPER_MODEL})...")
    print("   (Jika pertama kali, proses ini akan mengunduh model ±3GB)")
    print("-"*30)

    # Inisialisasi AI Captioner sekali saja (Large-V3 memakan RAM besar saat loading)
    try:
        captioner = VideoCaptioner(
            model_size= WHISPER_MODEL,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            download_root=str(MODELS_DIR),
            ffmpeg_path=FFMPEG_PATH,
            ffprobe_path=FFPROBE_PATH
        )
        logging.info("✅ AI Captioner siap digunakan({WHISPER_MODEL} - {DEVICE}).")
    except Exception as e:
        logging.warning(f"❌ GPU tidak tersedia {e} , Mencoba fallback ke CPU...")
        if DEVICE == "cuda":
            captioner = VideoCaptioner(model_size=WHISPER_MODEL, device="cpu", compute_type="int8")
        else:
            return

    # 🔄 LOOP UTAMA PROGRAM
    while True:
        print("\n" + "="*50)
        print("      YT TOOLKIT - AUTO CAPTION & PORTRAIT")
        print("="*50)
        print("1. Portrait Mode (AI Face Tracking 9:16 + Caption)")
        print("2. Landscape Mode (Standard 16:9 + Caption)")
        print("0. Keluar")
        
        choice = input("\nPilih tipe project: ").strip()
        
        if choice == "0":
            print("👋 Sampai jumpa!")
            break
            
        if choice not in ["1", "2"]:
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
                deno_path=DENO_PATH,
                use_gpu=USE_GPU
            )
            # Ambil metadata dan siapkan folder berdasarkan judul video
            downloader.setup_directories()

            # download video + audio
            v_path, a_path = downloader.download_both_separate()
            
            if not v_path or not a_path:
                print("❌ Gagal mendapatkan file video/audio. Cek koneksi atau URL.")
                continue
            
            # Cek apakah file JSON sudah ada (Skip Analisis AI jika resume)
            json_path = os.path.join(downloader.raw_dir, 'transcripts.json')
            
            if os.path.exists(json_path):
                print(f"⏩ [Step 1] File analisis ditemukan: {json_path}. Melewati analisis AI.")
            else:
                # Mendapatkan transkrip dan klip terbaik via Gemini
                summarizer = Summarize(api_key=api_key, out_dir=str(RAW_ASSETS_DIR), ffmpeg_path=FFMPEG_PATH)
                transcript = summarizer.get_transcript(url)
                # jalankan summarization
                summary = summarizer.generate_summarize(transcript, url, a_path)
                # simpan ringkasan + transkrip ke JSON
                json_path = summarizer.save_summary(url, summary, transcript, target_dir=downloader.raw_dir)

            # --- [STEP 2] REMUXING ---
            print("\n[Step 2/5] Menggabungkan Video & Audio (Remux)...")
            master_mkv = downloader.remux_video_audio(v_path, a_path)

            # --- [STEP 3] CLIPPING ---
            print("\n[Step 3/5] Memotong Klip Mentah (MKV)...")
            raw_clips = downloader.create_raw_clips(json_path)
            
            if not raw_clips:
                print("❌ Tidak ada klip yang berhasil dipotong.")
                continue

            # Menentukan direktori input dan output secara eksplisit di main.py
            video_base_path = RAW_ASSETS_DIR / downloader.asset_folder_name
            input_dir = video_base_path / "raw_clip_landscape"
            output_dir_portrait = video_base_path / "raw_clip_portrait"
            output_dir_portrait.mkdir(parents=True, exist_ok=True)
            
            # Menyiapkan folder output final yang terpisah agar Raw Assets tetap bersih
            video_final_dir = FINAL_OUTPUT_DIR / downloader.asset_folder_name
            video_final_dir.mkdir(parents=True, exist_ok=True)

            # --- [STEP 4] VISUAL PROCESSING ---
            processed_clips = []

            if choice == "1":
                print("\n[Step 4/5] Menjalankan AI Face Tracking (Portrait 9:16)...")
                # Mengambil file dari input_dir dan mengurutkannya
                raw_clip_files = sorted(list(Path(input_dir).glob("*.mkv")))
                
                # Inisialisasi Processor di luar loop agar model hanya dimuat sekali (Hemat Resource)
                proc = VideoProcessor(model_path=str(DETECTOR_MODEL_PATH), ffmpeg_path=FFMPEG_PATH, use_gpu=USE_GPU)
                try:
                    for clip_path in raw_clip_files:
                        out_name = f"portrait_{clip_path.stem}.mkv"
                        # Gunakan .resolve() untuk menghindari error 'Invalid argument' di Windows
                        output_file = (output_dir_portrait / out_name).resolve()
                        
                        if output_file.exists():
                            print(f"⏩ Portrait sudah ada: {out_name}")
                            processed_clips.append(output_file)
                            continue
                        
                        print(f"🎬 Processing Portrait: {clip_path.name}")
                        # Kirim path sebagai string absolut
                        proc.process_portrait(str(clip_path.resolve()), str(output_file))
                        processed_clips.append(output_file)
                        print(f"✅ Portrait Selesai: {out_name}")
                finally:
                    proc.close()
            else:
                print("\n[Step 4/5] Melewati Portrait (Menggunakan format Landscape)...")
                processed_clips = [Path(p).resolve() for p in raw_clips]

            # --- [STEP 5] AI CAPTIONING ---
            print(f"\n[Step 5/5] Menghasilkan Caption dengan {WHISPER_MODEL}...")
            for clip in processed_clips:
                # Tentukan nama file akhir (misal: portrait_clip_1_final.mkv)
                final_output = (video_final_dir / f"{clip.stem}_final.mkv").resolve()
                
                if final_output.exists():
                    print(f"⏩ Caption sudah ada: {final_output.name}")
                    continue
                
                print(f"📝 Mentranskrip: {clip.name}")
                # Kirim path absolut ke captioner
                success = captioner.process_full_caption(
                    video_path=str(clip), 
                    final_path=str(final_output),
                    fonts_dir=str(FONTS_DIR),
                    use_gpu=USE_GPU
                )
                
                if success:
                    print(f"✨ Hasil Akhir: {final_output.name}")
                else:
                    print(f"❌ Gagal memproses caption untuk: {clip.name}")

            print(f"\n🎉 SUKSES! Semua file tersedia di: {video_final_dir}")

        except Exception as e:
            print(f"\n❌ Terjadi kesalahan pada loop ini: {e}")
            input("\nTekan Enter untuk kembali ke menu...")

if __name__ == "__main__":
    main()