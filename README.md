# YT Toolkit - Auto Caption & Portrait

Sebuah toolkit canggih untuk konten kreator yang ingin mengotomatisasi proses editing video pendek (Shorts/Reels/TikTok). Toolkit ini mengunduh video YouTube, menganalisis momen viral menggunakan AI (Gemini), memotongnya, mengubah rasio ke portrait (9:16) dengan berbagai mode cerdas, dan menambahkan subtitle dinamis.

## Fitur Unggulan

- **Analisis Konten AI (Google Gemini):** Mencari momen paling menarik dan viral dari video panjang secara otomatis.
- **3 Mode Visual Cerdas:**
  - **Monologue Mode:** Tracking wajah otomatis untuk pembicara tunggal (MediaPipe).
  - **Podcast Mode:** Deteksi pembicara aktif untuk video diskusi/podcast 2 orang.
  - **Cinematic Mode:** Estetika vlog/dokumenter dengan background blur.
- **AI Captioning (Faster-Whisper):** Transkripsi super akurat dengan dukungan model `large-v3-turbo`.
- **Smart Hardware Fallback:** Otomatis mendeteksi kemampuan PC Anda (GPU High Performance -> GPU Low VRAM -> CPU) agar program tetap berjalan lancar di berbagai spesifikasi.
- **Auto Cookie Fix:** Solusi otomatis untuk mengatasi error download YouTube (HTTP 403) dengan mengambil akses dari browser.
- **Subtitle Dinamis:** Generate subtitle kata-per-kata dengan animasi highlight.

---

## Spesifikasi Sistem

| Komponen | Spesifikasi Minimal (Pas-pasan) | Spesifikasi Rekomendasi (Lancar) |
| :--- | :--- | :--- |
| **CPU** | Intel Core i5 Gen 8 / AMD Ryzen 5 | Intel Core i7 Gen 10+ / Ryzen 7 |
| **RAM** | 8 GB | 16 GB atau lebih |
| **GPU (VGA)** | Integrated Graphics (UHD/Vega) | NVIDIA RTX Series (Min. 4GB VRAM) |
| **Penyimpanan** | 5 GB ruang kosong (untuk model AI) | SSD (Sangat disarankan untuk akses model) |
| **OS** | Windows 10/11, Linux, atau macOS | Linux (Ubuntu) biasanya lebih efisien untuk AI |

## Panduan Instalasi & Penggunaan

Ikuti langkah-langkah ini untuk menjalankan aplikasi di komputer Anda.

### Langkah 1: Persiapan Awal

1.  **Instal Python:** Pastikan Anda memiliki Python versi 3.10 atau lebih baru (yt-dlp membutuhkan versi ini). Anda bisa mengunduhnya dari [python.org](https://www.python.org/downloads/). Saat instalasi, **centang kotak "Add Python to PATH"**.

2.  **Unduh Aset Pendukung:** Aplikasi ini membutuhkan beberapa file eksternal (FFmpeg, Model AI, Font).
    - Unduh semua aset dari link berikut: [Google Drive Aset](https://drive.google.com/drive/folders/1YacD0axuUOPOezJPiA8EuDnpwk7ZixNs?usp=sharing)
    - Ekstrak isinya dan letakkan folder `bin`, `models`, dan `fonts` langsung di dalam folder utama proyek ini.

### Langkah 2: Instalasi Dependensi

> **Tip:** Jika Anda menggunakan Windows, Anda dapat melewati langkah ini dan langsung menggunakan `run_app.bat` di Langkah 5. Script tersebut akan menginstal dependensi secara otomatis.

1.  **Buka Terminal:** Buka Command Prompt atau PowerShell di dalam folder proyek Anda. Cara cepat: di File Explorer, klik kanan di ruang kosong sambil menahan `Shift`, lalu pilih "Open PowerShell window here".

2.  **Buat Virtual Environment:** Ini adalah praktik terbaik untuk mengisolasi dependensi proyek.
    ```bash
    python -m venv .venv
    ```

3.  **Aktifkan Virtual Environment:**
    ```bash
    .venv\Scripts\activate
    ```
    *(Anda akan melihat `(.venv)` di awal baris terminal Anda jika berhasil).*

4.  **Instal Semua Paket:** Gunakan file `requirements.txt` untuk menginstal semua library Python yang dibutuhkan.
    ```bash
    pip install -r requirements.txt
    ```

### Langkah 3: Konfigurasi Kunci API

1.  Buat file baru di folder utama dan beri nama `.env`.
2.  Buka file `.env` tersebut dengan Notepad dan isi dengan format berikut, ganti dengan kunci API Anda:
    ```
    GEMINI_API_KEY="ISI_DENGAN_KUNCI_API_GEMINI_ANDA"
    ```
contoh :
    GEMINI_API_KEY=ABn89asfiuefjdufij290

### Langkah 4: Verifikasi Struktur Folder

Sebelum menjalankan aplikasi, pastikan struktur folder utama Anda terlihat seperti ini. Ini akan memastikan semua aset dan skrip berada di lokasi yang benar.

```
NAMA_FOLDER_PROYEK/
├── .venv/
├── fonts/
│   └── Poppins-Bold.ttf  (atau font pilihan Anda)
├── bin/
│   ├── deno.exe
│   ├── ffmpeg.exe
│   └── ffprobe.exe
├── models/
│   └── detector.tflite
├── yt_toolkit/
│   ├── __init__.py
│   ├── captioner.py
│   └── ... (file python lainnya)
├── .env
├── .gitignore
├── README.md
├── requirements.txt
├── run_app.bat
├── main.py
```

### Langkah 5: Jalankan Aplikasi

Anda dapat menjalankan aplikasi menggunakan **Launcher Otomatis** (disarankan) atau secara manual.

#### Opsi 1: Menggunakan `run_app.bat` (Windows)
Cukup klik ganda file `run_app.bat`. Script ini akan secara otomatis:
1. Membuat virtual environment (jika belum ada).
2. Menginstal dependensi (jika belum ada).
3. Menjalankan aplikasi.

#### Opsi 2: Menggunakan Terminal (Manual)
Setelah semua persiapan selesai dan virtual environment aktif, jalankan program utama:

```bash
python main.py
```

Aplikasi akan berjalan dan menampilkan menu utama di terminal Anda.

---

## Credits & Teknologi yang Digunakan

Proyek ini dapat terwujud berkat kerja keras komunitas open-source. Berikut adalah daftar teknologi dan library utama yang menjadi tulang punggung aplikasi ini:

- **Core AI & Machine Learning:**
  - **[Google Gemini](https://deepmind.google/technologies/gemini/)**: Otak utama untuk analisis konten, peringkasan, dan pemilihan momen viral.
  - **[Faster-Whisper](https://github.com/guillaumekln/faster-whisper)**: Engine transkripsi audio-ke-teks (ASR) yang sangat cepat dan efisien memori.
  - **[MediaPipe](https://developers.google.com/mediapipe)**: Solusi visi komputer on-device untuk pelacakan wajah real-time yang presisi.

- **Multimedia Processing:**
  - **[FFmpeg](https://ffmpeg.org/)**: Framework multimedia universal untuk memproses, memotong, dan menggabungkan video/audio.
  - **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**: Downloader video paling andal untuk berbagai platform.
  - **[OpenCV](https://opencv.org/)**: Library standar industri untuk pemrosesan gambar dan manipulasi frame video.

- **Utilities:**
  - **python-dotenv**: Manajemen konfigurasi environment yang aman.

Terima kasih kepada semua pengembang dan kontributor dari proyek-proyek di atas.