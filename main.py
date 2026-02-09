import os
import sys
import argparse
import multiprocessing
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

import logging
import warnings
from pathlib import Path
import shutil
warnings.filterwarnings("ignore")

from yt_toolkit.core.session import AppSession
from yt_toolkit.core.interface import CLI
from yt_toolkit.core.utils import extract_video_id

def process_automation(session, url, captioner):
    """Logika utama pemrosesan video (diekstrak dari loop lama)."""
    try:
        from yt_toolkit.engine.downloader import DownloadVidio, fetch_youtube_transcript
        from yt_toolkit.ai.summarizer import Summarize
        from yt_toolkit.core.pipeline import ClipProductionPipeline

        # --- 1. UNDUH ASET & ANALISIS KONTEN ---
        print("\n[1/3] Analisis & Download...")
        downloader = DownloadVidio(
            url=url, 
            temp_root=str(session.paths.TEMP_DIR),
            cookies_path=session.active_cookie_path,
            force_30fps=session.config.get('force_30fps', True)
        )
        
        # --- LOGIKA RESUME ---
        video_id = extract_video_id(url)
        existing_folder = None
        
        if video_id and session.paths.TEMP_SUMMARIZE.exists():
            for path in session.paths.TEMP_SUMMARIZE.iterdir():
                if path.is_dir() and path.name.endswith(f"-{video_id}"):
                    existing_folder = path
                    break
        
        if existing_folder:
            print(f"⏩ Folder aset ditemukan: {existing_folder.name}")
            downloader.asset_folder_name = existing_folder.name
            downloader.summarize_dir = str(session.paths.TEMP_SUMMARIZE / existing_folder.name)
            downloader.video_dir = str(session.paths.TEMP_VIDEO / existing_folder.name)
            downloader.video_title = existing_folder.name 
        else:
            downloader.setup_directories()

        json_path = Path(downloader.summarize_dir) / 'transcripts.json'
        
        if json_path.exists():
            print(f"⏩ File analisis ditemukan: {json_path.name}. Melewati analisis AI.")
        else:
            ai_audio_path = downloader.download_audio_for_ai()
            if not ai_audio_path:
                print("❌ Gagal mendapatkan file audio untuk AI.")
                return

            transcript = fetch_youtube_transcript(url, cookies_path=session.active_cookie_path)
            
            if not transcript:
                print("⚠️ Tidak ada CC. Menggunakan Fallback AI (Whisper)...", end='\r', flush=True)
                transcript = captioner.transcribe_for_ai(ai_audio_path)

            summarizer = Summarize(api_key=session.api_key, out_dir=downloader.summarize_dir)
            summary = summarizer.generate_summarize(transcript, url, ai_audio_path)
            json_path = Path(summarizer.save_summary(summary, transcript, target_dir=downloader.summarize_dir))

        print(f"\r✅ [1/3] Analisis selesai.{' ' * 50}\n", end="\n", flush=True)

        # --- [LANGKAH 2] PRODUKSI KLIP ---
        clips = downloader.get_clips()
        pipeline = ClipProductionPipeline(downloader, captioner, session.paths, session.config)
        
        # Jalankan Pipeline (Tanpa mode_choice)
        success = pipeline.run(clips, session.use_ai_gpu)
        
        session.release_captioner()
        
        if not success:
            return

        # --- [LANGKAH 3] FINALISASI ---
        print(f"\n[3/3] Finalisasi & Ekspor...")
        try:
            print(f"⏳ Menyalin ke folder Downloads...", end="\r", flush=True)
            video_final_dir = session.paths.TEMP_FINAL / downloader.asset_folder_name
            dest_dir = session.paths.USER_DOWNLOADS_DIR / session.config.get('final_output_subfolder', 'YT Toolkit Clips') / video_final_dir.name
            
            shutil.copytree(video_final_dir, dest_dir, dirs_exist_ok=True)
            print(f"✅ Selesai! Output tersimpan di:\n   📂 {dest_dir}", end="\n")

            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except ImportError:
                print('\a')
        except Exception as e:
            print(f"⚠️ Gagal menyalin hasil akhir ke folder Downloads: {e}")
            logging.warning(f"Gagal menyalin {video_final_dir} ke Downloads.", exc_info=True)

    except Exception as e:
        logging.critical(f"Terjadi kesalahan fatal: {e}", exc_info=True)
        print(f"\n❌ Error Fatal: {e}")

def main():
    # [PENTING] Diperlukan untuk multiprocessing (Pipeline Paralel) di Windows
    multiprocessing.freeze_support()

    # Setup CLI Arguments
    parser = argparse.ArgumentParser(description="YT Toolkit - Auto Caption & Portrait")
    parser.add_argument("--url", "-u", type=str, help="URL Video YouTube yang ingin diproses")
    parser.add_argument("--update-cookies", action="store_true", help="Jalankan wizard untuk memperbarui cookies")
    
    args = parser.parse_args()
    
    # Init Session
    session = AppSession()
    CLI.show_header()
    
    # Handle Cookies Update
    if args.update_cookies:
        CLI.run_cookie_wizard(session.paths.COOKIES_DIR)
        if not args.url:
            return # Keluar jika hanya ingin update cookies

    # Ensure API Key
    session.ensure_api_key()

    # Get URL (CLI or Input)
    url = args.url
    if not url:
        print("\nMasukkan URL YouTube untuk memulai (atau Ctrl+C untuk keluar):")
        try:
            url = input("👉 URL: ").strip()
        except KeyboardInterrupt:
            return
            
    if not url:
        print("❌ URL tidak boleh kosong.")
        return

    # Update cookies path automatically
    session.update_cookie_path()
    
    # Init AI Captioner
    captioner = session.get_captioner()
    if not captioner:
        return

    # Run Automation
    process_automation(session, url, captioner)
    
    # Cleanup
    session.cleanup()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Tangani Ctrl+C dengan bersih tanpa traceback yang menakutkan
        print("\n\n⛔ Program dihentikan paksa oleh pengguna (Ctrl+C).")