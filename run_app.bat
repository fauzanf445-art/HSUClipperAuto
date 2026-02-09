@echo off
setlocal
title YT Toolkit Launcher

REM Pindah ke direktori script berada (penting jika dijalankan sebagai Administrator)
cd /d "%~dp0"

echo ===================================================
echo      YT TOOLKIT - AUTO CLIPPER
echo ===================================================

REM 1. Cek apakah Python terinstal (Cek 'python' lalu 'py')
set PYTHON_CMD=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python tidak terdeteksi di sistem (PATH).
        echo Harap instal Python 3.10+ dari https://python.org dan centang "Add to PATH".
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
)

REM 2. Cek/Buat Virtual Environment
if not exist ".venv" (
    echo [INFO] Virtual environment tidak ditemukan. Membuat baru...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal membuat .venv. Cek izin folder.
        pause
        exit /b 1
    )
)

REM Selalu cek update dependensi saat launcher dijalankan
echo [INFO] Memastikan dependensi terupdate...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Gagal menginstal library. Cek koneksi internet atau requirements.txt.
    pause
    exit /b 1
)

REM 3. Jalankan Aplikasi
REM %* meneruskan argumen CLI (misal: --url "...") ke script python
echo [INFO] Memulai aplikasi...
.venv\Scripts\python.exe main.py %*

if %errorlevel% neq 0 (
    echo.
    echo [STOP] Aplikasi berhenti dengan error.
    pause
)
pause