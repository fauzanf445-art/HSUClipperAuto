from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')
if not API_KEY:
    print("[!] No GEMINI_API_KEY found in environment. Set it in .env or environment variables.")
else:
    client = genai.Client(api_key=API_KEY)
    try:
        print("Mengecek koneksi ke API...")
        response = client.models.list()
        print("\n--- DAFTAR MODEL DITEMUKAN ---")
        for model in response:
            print(f"Model Name: {getattr(model, 'name', str(model))}")
    except Exception as e:
        print("\n[!] KONEKSI GAGAL")
        print(f"Pesan Error: {e}")
        print("\nSaran Perbaikan:")
        print("1. Cek apakah API Key Anda sudah benar di https://aistudio.google.com/")
        print("2. Pastikan kuota gratis Anda tidak sedang dibatasi (Rate Limit).")