@echo off
title YT Toolkit Launcher

REM Pindah ke direktori tempat file ini berada (memastikan path benar)
cd /d "%~dp0"

echo ==================================================
echo      YT TOOLKIT - AUTO CLIP & CAPTION
echo ==================================================
echo.

REM 1. Cek apakah Python terinstall
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak terdeteksi!
    echo Mohon install Python 3.10+ dari python.org dan pastikan centang "Add to PATH".
    pause
    exit /b
)

REM 2. Cek Virtual Environment (.venv)
if not exist ".venv" (
    echo [SETUP] Virtual environment belum ada. Sedang membuat...
    python -m venv .venv
    
    echo [SETUP] Menginstall library dari requirements.txt...
    echo Mohon tunggu, proses ini membutuhkan koneksi internet...
    
    REM Menggunakan pip dari dalam venv secara langsung agar lebih aman
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal menginstall library. Cek koneksi internet Anda.
        pause
        exit /b
    )
    echo [SETUP] Instalasi selesai!
)

REM 3. Jalankan Program Utama
echo.
echo [START] Menjalankan aplikasi...
echo --------------------------------------------------

REM Memanggil python dari .venv secara eksplisit untuk memastikan library terbaca
".venv\Scripts\python.exe" main.py

REM 4. Tahan jendela agar tidak langsung tertutup saat selesai/error
echo.
echo Program berhenti. Tekan tombol apa saja untuk keluar...
pause >nul