import os
import sys
import logging
import shutil
import yaml
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

from .utils import setup_paths
from .interface import CLI

class AppSession:
    """
    Mengelola state global aplikasi, konfigurasi, dan siklus hidup resource (Session Manager).
    Menyederhanakan main.py dengan menyembunyikan detail inisialisasi.
    """
    def __init__(self):
        self.paths = setup_paths()
        self.config = {}
        self.api_key = None
        self.captioner = None
        self.use_ai_gpu = False
        self.active_cookie_path = None
        self.whisper_model_name = "large-v3-turbo"

        # Inisialisasi awal otomatis
        self._load_configuration()
        self._setup_logging()

    def _load_configuration(self):
        """Memuat config.yaml dan .env."""
        # 1. Muat config.yaml
        try:
            with open(self.paths.CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            print("❌ FATAL: File 'config.yaml' tidak ditemukan. Pastikan file tersebut ada di folder utama.")
            sys.exit(1)

        # 2. Muat .env
        load_dotenv(dotenv_path=self.paths.ENV_FILE)
        self.api_key = os.getenv('GEMINI_API_KEY')

        # 3. Validasi Model Whisper
        from faster_whisper import available_models
        self.whisper_model_name = self.config.get('whisper_model', 'large-v3-turbo')
        if self.whisper_model_name not in available_models() and "turbo" not in self.whisper_model_name:
            logging.warning(f"⚠️ Model '{self.whisper_model_name}' mungkin tidak valid. Model yang tersedia: {available_models()}")

    def _setup_logging(self):
        """Konfigurasi logging terpusat."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        if root_logger.hasHandlers():
            root_logger.handlers.clear()
            
        file_handler = RotatingFileHandler(self.paths.LOG_FILE, mode='a', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        root_logger.addHandler(console_handler)

        # Bungkam library yang berisik
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
        logging.getLogger("absl").setLevel(logging.INFO)

    def ensure_api_key(self):
        """Wrapper untuk CLI.ensure_api_key yang memperbarui state session."""
        self.api_key = CLI.ensure_api_key(self.api_key, self.paths.ENV_FILE)

    def change_api_key(self):
        """Wrapper untuk CLI.change_api_key."""
        self.api_key = CLI.change_api_key(self.api_key, self.paths.ENV_FILE)

    def update_cookie_path(self):
        """Mencari file cookie terbaru di folder cookies."""
        self.active_cookie_path = None
        self.paths.COOKIES_DIR.mkdir(exist_ok=True)
        try:
            cookie_files = list(self.paths.COOKIES_DIR.glob("*.txt"))
            if cookie_files:
                self.active_cookie_path = str(max(cookie_files, key=os.path.getmtime))
            else:
                logging.warning("⚠️ File cookie tidak ditemukan. Gunakan menu 'Perbarui Cookies' jika download gagal.")
        except Exception as e:
            logging.error(f"Gagal mencari file cookie: {e}", exc_info=True)

    def get_captioner(self):
        """Lazy loading untuk VideoCaptioner. Hanya dimuat saat dibutuhkan."""
        if self.captioner is None:
            from yt_toolkit.ai.captioner import VideoCaptioner
            print(f"⏳ Menyiapkan AI...", end="\r", flush=True)
            try:
                self.captioner = VideoCaptioner.create_auto_device(
                    model_size=self.whisper_model_name,
                    download_root=str(self.paths.MODELS_DIR)
                )
                self.use_ai_gpu = (self.captioner.device == "cuda")
            except RuntimeError as e:
                logging.critical(f"Gagal memuat AI Captioner: {e}")
                print("❌ Error Fatal: AI tidak dapat dimuat.")
                return None
        return self.captioner

    def release_captioner(self):
        """Melepaskan captioner dan mereset state agar bisa di-init ulang nanti."""
        if self.captioner:
            # Note: Pipeline biasanya sudah memanggil .release(), tapi kita pastikan referensi dihapus
            if hasattr(self.captioner, 'model'):
                self.captioner.release()
            self.captioner = None

    def cleanup(self, full_clean=False):
        """Membersihkan resource saat keluar aplikasi."""
        config_enabled = self.config.get('cleanup_enabled', True)
        
        if not config_enabled and not full_clean:
            return

        print("\n👋 Menutup aplikasi...", end="\n", flush=True)
        logging.shutdown()
        
        if full_clean:
            print("\n🧹 Membersihkan cache & log...", end="", flush=True)
            for log_file in self.paths.BASE_DIR.glob("debug.log*"):
                try: os.remove(log_file)
                except: pass
            
        temp_dir = self.paths.TEMP_DIR
        if temp_dir.exists():
            try: shutil.rmtree(temp_dir)
            except: pass