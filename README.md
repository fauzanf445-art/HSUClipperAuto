# YT Toolkit - Auto Caption & Portrait

Sebuah toolkit untuk mengunduh video YouTube, menganalisisnya dengan AI untuk menemukan momen viral, memotongnya menjadi klip pendek, mengubah formatnya menjadi portrait (opsional), dan secara otomatis menghasilkan subtitle dengan gaya kata-per-kata.

## Fitur

- **Analisis AI (Google Gemini):** Menganalisis audio dan transkrip untuk merekomendasikan klip-klip potensial.
- **AI Face Tracking (MediaPipe):** Secara otomatis mengubah video landscape menjadi format portrait (9:16) dengan menjaga wajah tetap di tengah.
- **AI Captioning (Faster-Whisper):** Menghasilkan transkripsi akurat dengan timestamp per kata.
- **Subtitle Dinamis:** Membuat subtitle dengan efek highlight dan pop-up secara otomatis.
- **Akselerasi GPU:** Mendukung CUDA untuk proses AI (Whisper) dan encoding video (FFmpeg NVENC) untuk performa maksimal.

---

## Panduan Instalasi & Penggunaan

Ikuti langkah-langkah ini untuk menjalankan aplikasi di komputer Anda.

### Langkah 1: Persiapan Awal

1.  **Instal Python:** Pastikan Anda memiliki Python versi 3.12 atau versi stable lebih baru. Anda bisa mengunduhnya dari [python.org](https://www.python.org/downloads/). Saat instalasi, **centang kotak "Add Python to PATH"**.

2.  **Unduh Aset Eksternal:** Aplikasi ini membutuhkan beberapa program dan model. Unduh dan letakkan file-file berikut di dalam folder utama proyek:
    - **FFmpeg & FFprobe:** Unduh dari [sini](https://www.gyan.dev/ffmpeg/builds/) (ambil `ffmpeg-release-full.zip`). Ekstrak dan salin `ffmpeg.exe` dan `ffprobe.exe` dari folder `bin` ke folder utama proyek Anda.
    - **Deno:** Unduh [sini](https://github.com/denoland/deno/releases) dari halaman rilis Deno dan letakkan 'deno.exe' di folder utama.
    - **Face Detector Model:** Unduh file [sini](https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite) dari MediaPipe Models  dan ganti namanya menjadi `detector.tflite`. Letakkan di folder utama.

3.  **Siapkan Folder Font:** Buat folder bernama `fonts` di direktori utama dan letakkan file font yang Anda inginkan di dalamnya (misalnya `Poppins-Bold.ttf`).

### Langkah 2: Instalasi Dependensi

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
2.  Buka file `.env` tersebut dengan Notepad dan isi dengan format berikut, ganti dengan kunci API Anda(tidak menggunakan tanda kutip),:
    ```
    GEMINI_API_KEY="ISI_DENGAN_KUNCI_API_GEMINI_ANDA"
    HF_TOKEN="ISI_DENGAN_TOKEN_HUGGINGFACE_ANDA"
    ```
contoh :
    GEMINI_API_KEY=ABn89asfiuefjdufij290
    HF_TOKEN=793j3nkdfasynokokmv769


### Langkah 4: Jalankan Aplikasi



Setelah semua persiapan selesai dan virtual environment aktif, jalankan program utama:

```bash
python main.py
```

Aplikasi akan berjalan dan menampilkan menu utama di terminal Anda.
