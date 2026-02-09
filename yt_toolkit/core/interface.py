import os
import sys
from .utils import update_cookies_from_browser

class CLI:
    """
    Menangani interaksi antarmuka pengguna (CLI): Menu, Input, dan Wizard.
    Memisahkan logika tampilan dari logika orkestrasi utama.
    """

    @staticmethod
    def show_header():
        print("\nYT TOOLKIT - AUTO CLIP & CAPTION")

    @staticmethod
    def show_menu():
        """Menampilkan menu utama dan meminta input pengguna."""
        print("\n" + "="*40)
        print("      MENU YT TOOLKIT")
        print("="*40)
        print("1. Monologue Mode (Face Tracking)")
        print("2. Podcast Mode (Smart Static)")
        print("3. Cinematic Mode (Blur BG)")
        print("4. Ganti API Key")
        print("5. Perbarui Cookies")
        print("6. Refresh App")
        print("0. Keluar")
        return input("\nPilihan Anda (0-5):").strip()

    @staticmethod
    def ensure_api_key(api_key, env_file_path):
        """
        Memastikan API Key valid tersedia.
        Jika belum ada/invalid, meminta input user dalam loop hingga valid.
        """
        while True:
            from yt_toolkit.ai.summarizer import Summarize
            # 1. Jika API Key ada, validasi dulu
            if api_key:
                print(f"⏳ Memvalidasi API Key...", end="\r", flush=True)
                if Summarize.validate_api_key(api_key):
                    print(f"\r✅ API Key terkonfirmasi valid!{' '*30}", end="\r", flush=True)
                    os.environ['GEMINI_API_KEY'] = api_key
                    return api_key
                else:
                    print(f"❌ API Key tidak valid atau kadaluarsa.{' '*30}")
                    api_key = None # Reset agar masuk ke mode input
            
            # 2. Jika tidak ada key atau invalid, minta input user
            print(f"\n⚠️  Konfigurasi API Key Diperlukan ({env_file_path})")
            print("   Dapatkan key di: https://aistudio.google.com/app/apikey")
            user_input_key = input("👉 Masukkan Gemini API Key: ").strip()
            
            if not user_input_key:
                print("❌ API Key wajib diisi. Program berhenti.")
                sys.exit(1)

            # 3. Cek input user sebelum disimpan
            print(f"⏳ Memeriksa kunci...", end="\r", flush=True)
            if Summarize.validate_api_key(user_input_key):
                with open(env_file_path, "w", encoding="utf-8") as f:
                    f.write(f'GEMINI_API_KEY="{user_input_key}"\n')
                print(f"✅ File .env berhasil diperbarui!{' '*30}")
                api_key = user_input_key 
            else:
                print(f"❌ API Key yang Anda masukkan salah. Silakan coba lagi.{' '*20}")

    @staticmethod
    def change_api_key(current_key, env_file_path):
        """Wizard untuk mengganti API Key."""
        from yt_toolkit.ai.summarizer import Summarize
        print("\n--- GANTI API KEY ---")
        print(f"Key saat ini: {current_key[:5]}...{current_key[-5:] if current_key else 'None'}")
        new_key = input("👉 Masukkan Gemini API Key baru: ").strip()
        
        if not new_key:
            print("⚠️ Input kosong. Kembali ke menu utama.")
            return current_key

        print(f"⏳ Memvalidasi API Key baru...", end="\r", flush=True)
        if Summarize.validate_api_key(new_key):
            with open(env_file_path, "w", encoding="utf-8") as f:
                f.write(f'GEMINI_API_KEY="{new_key}"\n')
            os.environ['GEMINI_API_KEY'] = new_key
            print(f"✅ API Key berhasil diperbarui dan disimpan!{' '*30}")
            return new_key
        else:
            print(f"❌ API Key tidak valid. Perubahan dibatalkan.{' '*30}")
            return current_key

    @staticmethod
    def run_cookie_wizard(cookies_dir):
        """Wizard interaktif untuk memperbarui cookies dari browser."""
        print("\n--- PERBARUI COOKIES OTOMATIS ---")
        print("Pilih browser yang Anda gunakan untuk login YouTube:")
        print("1. Google Chrome")
        print("2. Microsoft Edge")
        print("3. Firefox")
        print("4. Opera")
        print("5. Brave")
        
        b_choice = input("Pilih browser (1-5): ").strip()
        browser_map = {"1": "chrome", "2": "edge", "3": "firefox", "4": "opera", "5": "brave"}
        
        selected_browser = browser_map.get(b_choice)
        if selected_browser:
            print(f"\n⚠️  PENTING: Mohon TUTUP browser {selected_browser} agar proses berhasil.")
            input("Tekan Enter jika browser sudah ditutup...")
            target_cookie_file = cookies_dir / f"{selected_browser}_cookies.txt"
            update_cookies_from_browser(selected_browser, str(target_cookie_file))
        else:
            print("❌ Pilihan browser tidak valid.")

    @staticmethod
    def get_youtube_url():
        return input("Masukkan URL YouTube: ").strip()
