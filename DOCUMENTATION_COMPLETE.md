# YT Downloader - Complete Documentation

**Combined Reference for All Modules & Features**

---

## 📖 Table of Contents

1. [INDEX](#index-navigation-hub)
2. [README](#readme---main-project-overview)
3. [GETTING_STARTED](#getting_started---quick-start-guide)
4. [REFACTOR_SUMMARY](#refactor_summary---changes-overview)
5. [REFACTOR_STATUS](#refactor_status---refactor-completion-status)
6. [REFACTOR_DOCUMENTATION](#refactor_documentation---complete-api-docs)
7. [QUICK_REFERENCE](#quick_reference---cheat-sheet)
8. [FORMAT_CHANGE_MKV](#format_change_mkv---output-format-update)
9. [GUIDE_ADD_CAPTIONS](#guide_add_captions---caption-workflow)
10. [CAPTIONS_USAGE](#captions_usage---whisper-transcription)

---

# INDEX - Navigation Hub

## 🎯 Mulai Di Sini

**Baru pertama kali?** → Baca [GETTING STARTED](#getting_started---quick-start-guide) ⭐

---

## 📖 Dokumentasi Tersedia

### 1. 🚀 GETTING_STARTED - Panduan Cepat
- Setup awal & instalasi
- 5 scenario lengkap dengan code
- Troubleshooting
- Tips & trik
- FAQ

**Waktu baca:** 10-15 menit
**Cocok untuk:** Pemula, ingin langsung praktek

---

### 2. 📋 REFACTOR_SUMMARY - Ringkasan Perubahan
- Before vs After
- Fitur baru
- Method mapping
- Architecture comparison
- Migration guide

**Waktu baca:** 5-10 menit
**Cocok untuk:** Yang ingin tahu apa berubah

---

### 3. 📚 REFACTOR_DOCUMENTATION - Dokumentasi Lengkap
- Detail setiap class
- Detail setiap method
- Return types & parameters
- Struktur direktori
- Workflow examples
- API reference

**Waktu baca:** 20-30 menit
**Cocok untuk:** Developer, ingin detail teknis

---

### 4. 🎯 QUICK_REFERENCE - Cheat Sheet
- Copy-paste code snippets
- Common workflows
- Troubleshooting
- Performance tips
- Encoding options

**Waktu baca:** 2-3 menit
**Cocok untuk:** Di-reference saat coding

---

## 🏗️ Struktur Kode

```
yt_toolkit.py (merged module)
├── Class: Summarize
│   ├── extract_video_id()
│   ├── get_transcript()
│   ├── summarize()
│   └── save_summary()
│
├── Class: DownloadVidio
│   ├── download_video_only()
│   ├── download_audio_only()
│   ├── download_both(remux)
│   ├── remux_video_audio()
│   └── fix_video()
│
├── Class: ClipVidio
│   ├── time_to_seconds()
│   ├── add_transcripts()
│   ├── clip_video_from_json()
│   └── run()  ← Menu interaktif
│
├── Class: Caption
│   ├── _format_timestamp_srt()
│   ├── _write_srt()
│   ├── _find_clips()
│   ├── transcribe_clips()
│   └── _embed_srt()
│
└── CLI: _cli()
```

---

## 🚀 5-Menit Quick Start

### 1. Import
```python
from yt_toolkit import Summarize, DownloadVidio, ClipVidio, Caption
```

### 2. Download
```python
downloader = DownloadVidio("https://youtube.com/watch?v=ID", video_id="video1")
_, _, master = downloader.download_both(remux=True)
```

### 3. Clip
```python
clipper = ClipVidio(video_id="video1")
clipper.run()  # Menu muncul, follow instructions
```

**Done!** Clips ada di `output/final_output/video1/`

---

## 📋 Fitur Utama

### ✅ Summarize Class
- [x] Extract video ID dari URL
- [x] Get transcript dari YouTube
- [x] Summarize dengan Gemini
- [x] Save summary ke JSON

### ✅ DownloadVidio Class
- [x] Download video saja (best quality)
- [x] Download audio saja (MP3)
- [x] Download video + audio dengan opsi remux
- [x] Fix video codec
- [x] Remux audio-video

### ✅ ClipVidio Class
- [x] Buat clips dari JSON
- [x] Support subtitle/transcript
- [x] Interactive menu
- [x] Time format parser (H:MM:SS, M:SS, SS)
- [x] Progress indication

### ✅ Caption Class
- [x] Transcribe clips dengan Whisper
- [x] Generate SRT files
- [x] Embed subtitle ke MKV
- [x] Support multiple models
- [x] Dry-run mode for testing

### ✅ User Experience
- [x] Menu interaktif dengan konfirmasi
- [x] Logging informatif
- [x] Error handling
- [x] Flexible output options
- [x] CLI support

---

## 🎯 Quick Navigation

### Saya ingin...

| Kebutuhan | Section | Bagian |
|-----------|---------|--------|
| Mulai cepat | GETTING_STARTED | Scenario 1-5 |
| Download video | QUICK_REFERENCE | DOWNLOADVIDIO CLASS |
| Buat clips | QUICK_REFERENCE | CLIPVIDIO CLASS |
| Atur caption | GUIDE_ADD_CAPTIONS | Cara 1-3 |
| Tahu apa berubah | REFACTOR_SUMMARY | Before vs After |
| Detail teknis | REFACTOR_DOCUMENTATION | API Reference |
| Troubleshoot error | GETTING_STARTED | Troubleshooting |
| Copy-paste code | QUICK_REFERENCE | Cheat Sheet |

---

## 🗂️ File Structure After Using

```
📁 output/
├── 📁 raw_assets/{video_id}/
│   ├── transcripts.json          ← Input JSON
│   ├── subtitles.srt             ← Optional
│   └── *.mkv *.mp3               ← Downloaded files
│
└── 📁 final_output/{video_id}/
    └── *.mkv                     ← Output clips
```

---

## 🔧 Installation

```bash
# 1. Install requirements
pip install yt-dlp openai-whisper google-genai python-dotenv youtube-transcript-api

# 2. Download FFmpeg
# From: https://ffmpeg.org/download.html
# Or: choco install ffmpeg

# 3. Put ffmpeg.exe in script directory (Windows)
# Or: Ensure ffmpeg is in PATH

# 4. Setup .env file
echo GEMINI_API_KEY=your_key_here > .env

# 5. Run!
python your_script.py
```

---

## 📈 Next Steps

1. Read GETTING_STARTED section
2. Run example scripts
3. Try your first download
4. Try your first clipping
5. Build your own workflow!

---

---

# README - Main Project Overview

## YouTube Toolkit (Professional)

This project provides four main components combined in a single module:

- `yt_toolkit.py` (merged module) — unified toolkit with four classes:
  - `Summarize` : fetch & summarize transcript (Gemini / YouTubeTranscriptApi)
  - `DownloadVidio` : download video/audio using yt_dlp
  - `ClipVidio` : create clips from master video using transcripts.json
  - `Caption` : transcribe clips using Whisper and write/embed SRT

## Quick start

1. Create a `.env` file in the project root with your Gemini API key:

   ```
   GEMINI_API_KEY=your_key_here
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Ensure `ffmpeg` is installed and reachable (or place `ffmpeg.exe` in project root).

4. Use the classes directly or via CLI:

   ```bash
   python yt_toolkit.py download --url "https://youtube.com/watch?v=ID" --video-id myid
   python yt_toolkit.py clip --video-id myid
   python yt_toolkit.py caption --video-id myid --dry-run
   ```

## Folder layout created by the toolkit

- `raw_assets/{video_id}/...` — downloaded master video and audio
- `final_output/{video_id}/` — generated clips (MKV format)

## Notes

- The Summarize class expects the Gemini model to return valid JSON (the prompt requests strict JSON). If the model returns non-JSON, the raw text will be saved under the `summary` JSON under the `raw` key.
- Keep your `.env` out of source control (`.gitignore` already ignores it).
- Output format for clips is now **MKV** (Matroska) for better subtitle support.
- Captions are generated using **Whisper ASR** (openai-whisper).

---

# GETTING_STARTED - Quick Start Guide

## 🚀 Panduan Cepat Mulai - Downloader & VideoClipper

## Instalasi & Setup Awal

### Step 1: Pastikan Requirements Terpenuhi
```bash
pip install yt-dlp openai-whisper google-genai
# ffmpeg sudah ter-install?
ffmpeg -version
```

### Step 2: Struktur Folder
```
📁 YT downloader/
├── yt_toolkit.py
├── ffmpeg.exe          (di Windows)
└── output/             (dibuat otomatis)
```

---

## Scenario 1: Download Video Saja

**Kapan digunakan:** Saat Anda hanya butuh video, audio bisa ambil dari tempat lain

```python
from yt_toolkit import DownloadVidio

# Buat downloader object
downloader = DownloadVidio(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    video_id="rickroll"
)

# Download hanya video
video_path = downloader.download_video_only()

print(f"✅ Video disimpan di: {video_path}")
# Output: ./output/raw_assets/rickroll/video_only.mkv
```

---

## Scenario 2: Download Audio Saja (MP3)

**Kapan digunakan:** Saat Anda ingin extract audio dari video YouTube

```python
from yt_toolkit import DownloadVidio

downloader = DownloadVidio(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    video_id="rickroll"
)

# Download hanya audio (MP3)
audio_path = downloader.download_audio_only()

print(f"✅ Audio disimpan di: {audio_path}")
# Output: ./output/raw_assets/rickroll/audio_only.mp3
```

---

## Scenario 3: Download Video + Audio, Langsung Remux

**Kapan digunakan:** Saat Anda ingin 1 file video dengan audio terbaik

```python
from yt_toolkit import DownloadVidio

downloader = DownloadVidio(
    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    video_id="rickroll"
)

# Download keduanya dan gabung jadi 1 file
video, audio, master = downloader.download_both(remux=True)

if master:
    print(f"✅ Video + Audio sudah di-remux: {master}")
    # Output: ./output/raw_assets/rickroll/master.mkv
else:
    print("❌ Gagal!")
```

---

## Scenario 4: Buat Clip dari JSON (dengan Menu Interaktif)

### Step A: Siapkan JSON File

Letakkan file `transcripts.json` di folder: `output/raw_assets/rickroll/`

**Isi file:**
```json
{
  "video_title": "Rick Roll Video",
  "clips": [
    {
      "start_time": "0:10",
      "end_time": "0:45",
      "title": "Intro"
    },
    {
      "start_time": "1:00",
      "end_time": "2:30",
      "title": "Main Part"
    }
  ]
}
```

### Step B: Jalankan ClipVidio

```python
from yt_toolkit import ClipVidio

clipper = ClipVidio(video_id="rickroll")

# Menu interaktif akan muncul
clipper.run()
```

### Step C: Menu akan menampilkan:

```
═══════════════════════════════════════════
🎬 VIDEO CLIPPER - Interactive Menu
═══════════════════════════════════════════

✓ Available videos in ./raw_assets/rickroll:
  1. master.mkv
  Select video (number or leave empty for first): 

--- Subtitle/Transcript Options ---
1. Add subtitles (jika file .srt tersedia)
2. No subtitles
Select option (1 or 2): 2

Summary:
  Video input: ./raw_assets/rickroll/master.mkv
  Output dir: ./final_output/rickroll
  Use subtitles: False

▶️  Proceed with clipping? (yes/no): yes

⏳ Processing clips...
✓ Clip 1 done: 01_Intro.mkv (35 sec)
✓ Clip 2 done: 02_Main_Part.mkv (90 sec)

✅ All clips completed successfully!
📁 Output saved to: ./final_output/rickroll
```

**Hasil:** File MKV clips ada di `final_output/rickroll/`

---

## Scenario 5: Complete Workflow (Download → Summarize → Clip → Caption)

**Skenario lengkap dari download sampai dapat clips dengan caption:**

```python
from yt_toolkit import Summarize, DownloadVidio, ClipVidio, Caption
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

# ========== STEP 1: SUMMARIZE ==========
print("📝 Step 1: Summarize video")
print("="*60)

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
video_id = "rickroll"

summarizer = Summarize(api_key="your_key")
transcript = summarizer.get_transcript(url)
summary = summarizer.summarize(transcript)
summarizer.save_summary(url, summary, transcript_text=transcript)

print("✅ Summary saved\n")

# ========== STEP 2: DOWNLOAD ==========
print("📥 Step 2: Download from YouTube")
print("="*60)

downloader = DownloadVidio(url, video_id=video_id)
video, audio, master = downloader.download_both(remux=True)

if not master:
    print("❌ Download gagal!")
    exit()

print(f"✅ Download selesai: {master}\n")

# ========== STEP 3: BUAT CLIPS ==========
print("✂️  Step 3: Create clips")
print("="*60 + "\n")

clipper = ClipVidio(video_id=video_id)
clipper.run()  # Menu interaktif

# ========== STEP 4: ADD CAPTIONS ==========
print("\n📝 Step 4: Add captions")
print("="*60 + "\n")

caption = Caption()
caption.transcribe_clips(video_id, dry_run=False, model_name="small", embed=True)

print("\n" + "="*60)
print("✅ SELESAI! Semua clips sudah ada subtitle!")
print("="*60)
```

---

## Struktur Output

Setelah menjalankan semua scenario di atas, folder Anda akan terlihat seperti:

```
📁 output/
├── 📁 raw_assets/rickroll/
│   ├── transcripts.json          ← Summary dari Gemini
│   ├── transcript.txt            ← Full transcript
│   ├── video_only.mkv            ← dari scenario 1
│   ├── audio_only.mp3            ← dari scenario 2
│   ├── temp_video.mkv            ← dari scenario 3
│   ├── temp_audio.m4a            ← dari scenario 3
│   └── master.mkv                ← dari scenario 3 atau 4
│
└── 📁 final_output/rickroll/
    ├── 01_Intro.mkv              ← Clip dengan subtitle
    ├── 01_Intro.srt              ← Subtitle file
    ├── 02_Main_Part.mkv
    ├── 02_Main_Part.srt
    └── ...
```

---

## Troubleshooting

### ❌ Error: "ffmpeg not found"
**Solusi:**
1. Download FFmpeg dari https://ffmpeg.org/download.html
2. Letakkan `ffmpeg.exe` di folder yang sama dengan script
3. Atau install dengan: `choco install ffmpeg`

### ❌ Error: "JSON not found"
**Solusi:**
- Pastikan file `transcripts.json` ada di:
  ```
  output/raw_assets/{video_id}/transcripts.json
  ```

### ❌ Download sangat lambat
**Solusi:**
- Cek koneksi internet
- Gunakan VPN jika YouTube diblokir
- Coba download dengan format lebih rendah

### ❌ Clip output corrupted
**Solusi:**
- Coba gunakan `fix_video()` sebelum clipping:
  ```python
  fixed = downloader.fix_video(master)
  clipper.clip_video_from_json(fixed)
  ```

---

## Tips & Trik

### ✅ Tip 1: Batch Download Banyak Video

```python
from yt_toolkit import DownloadVidio

urls = [
    ("https://youtube.com/watch?v=ID1", "video1"),
    ("https://youtube.com/watch?v=ID2", "video2"),
    ("https://youtube.com/watch?v=ID3", "video3"),
]

for url, vid_id in urls:
    downloader = DownloadVidio(url, video_id=vid_id)
    _, _, master = downloader.download_both(remux=True)
    print(f"✅ {vid_id} downloaded")
```

### ✅ Tip 2: Gunakan Error Handling
```python
from yt_toolkit import DownloadVidio

try:
    downloader = DownloadVidio(url, video_id="video1")
    _, _, master = downloader.download_both(remux=True)
    
    if not master:
        print("❌ Remux failed!")
        exit()
        
except Exception as e:
    print(f"❌ Error: {e}")
    exit()
```

### ✅ Tip 3: Custom Output Directory
```python
from yt_toolkit import ClipVidio

clipper = ClipVidio(
    video_id="rickroll",
    base_output_dir="/custom/path",
    output_dir="/custom/clips/output"
)
```

### ✅ Tip 4: Logging untuk Debug
```python
import logging

logging.basicConfig(
    level=logging.DEBUG,  # Lebih detail
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Sekarang semua aktivitas terlihat
```

---

## Quick Reference Commands

| Tugas | Kode |
|------|------|
| Download video saja | `downloader.download_video_only()` |
| Download audio saja | `downloader.download_audio_only()` |
| Download + remux | `downloader.download_both(remux=True)` |
| Fix codec | `downloader.fix_video(path)` |
| Buat clip (menu) | `clipper.run()` |
| Buat clip (code) | `clipper.clip_video_from_json(video)` |
| Konversi time | `clipper.time_to_seconds("1:30")` |
| Transcribe clips | `caption.transcribe_clips(video_id)` |
| Dry-run transcribe | `caption.transcribe_clips(video_id, dry_run=True)` |

---

## Next Steps

1. ✅ Setup FFmpeg
2. ✅ Install requirements: `pip install -r requirements.txt`
3. ✅ Create .env with API key
4. ✅ Try Scenario 1 (download video only)
5. ✅ Try Scenario 5 (complete workflow)

---

## FAQ

**Q: Berapa lama download untuk video 1 jam?**
A: 2-5 menit tergantung kualitas dan kecepatan internet

**Q: Berapa lama untuk buat 10 clips?**
A: 50-150 menit tergantung durasi dan setting quality

**Q: Bisa ganti format output?**
A: Ya, edit codec dan preset di dalam code

**Q: Bisa parallel download?**
A: Ya, gunakan ThreadPoolExecutor untuk multiple videos

---

---

# REFACTOR_SUMMARY - Changes Overview

## 📋 Ringkasan Refactor: Dari File Terpisah Menjadi Unified Module

---

## File Organization Change

### BEFORE:
```
youtube_summarizer.py
video_clipper.py
generate_captions.py
example_usage.py
main.py
new.py
```

### AFTER:
```
yt_toolkit.py ← All merged into single module
main.py
requirements.txt
DOCUMENTATION_COMPLETE.md ← Combined docs
```

---

## Classes Now Available

All classes are now in `yt_toolkit.py`:

- **Summarize** - Fetch & summarize transcript
- **DownloadVidio** - Download video/audio
- **ClipVidio** - Create clips from JSON
- **Caption** - Transcribe & embed subtitles

---

## Quality Improvements

✅ **Separation of concerns** - Each class has single responsibility  
✅ **Reusability** - Use any class independently  
✅ **Documentation** - Consolidated & easier to navigate  
✅ **Error handling** - Better across all classes  
✅ **CLI support** - Built-in command-line interface  

---

# REFACTOR_STATUS - Refactor Completion Status

## ✅ STATUS: SELESAI! 

Refactor completed successfully. All modules merged, docs consolidated, Python files cleaned up.

### What Was Done:

1. ✅ Merged 4 Python files into `yt_toolkit.py`
2. ✅ Deleted redundant Python files
3. ✅ Consolidated all documentation
4. ✅ Created single comprehensive docs file

### Repository Status:

**Syntax Check:** ✅ PASSED  
**Import Check:** ✅ PASSED  
**Documentation:** ✅ COMPLETE & CONSOLIDATED  
**Examples:** ✅ PROVIDED IN GETTING_STARTED  

---

# REFACTOR_DOCUMENTATION - Complete API Docs

## Class 1: Summarize

### Constructor
```python
Summarize(api_key: Optional[str] = None, model: str = 'gemini-flash-latest', out_dir: Optional[str] = None)
```

### Methods

#### `extract_video_id(url: str) -> Optional[str]`
Extract YouTube video ID from URL.

**Returns:** Video ID or None

---

#### `get_transcript(video_url: str, prefer_langs=('id', 'en')) -> str`
Fetch transcript from YouTube.

**Parameters:**
- `video_url`: YouTube URL
- `prefer_langs`: Languages to try (in order)

**Returns:** Full transcript text

---

#### `summarize(transcript_text: str) -> str`
Summarize transcript using Gemini.

**Returns:** JSON string with summary and clips

---

#### `save_summary(video_url: str, summary_text: str, prefix: str = 'summary', transcript_text: Optional[str] = None) -> str`
Save summary to JSON file.

**Returns:** Path to saved JSON

---

## Class 2: DownloadVidio

### Constructor
```python
DownloadVidio(url: str, base_output_dir: str = None, video_id: str = None)
```

### Methods

#### `download_video_only() -> str`
Download only video (best quality).

**Returns:** Path to video file or None

---

#### `download_audio_only() -> str`
Download only audio (MP3).

**Returns:** Path to audio file or None

---

#### `download_both(remux: bool = True) -> tuple`
Download video and audio.

**Parameters:**
- `remux`: If True, combine into single file

**Returns:** Tuple `(video_path, audio_path, remuxed_path)`

---

#### `remux_video_audio(video_path: str, audio_path: str, output_path: str) -> bool`
Combine video and audio.

**Returns:** True if successful

---

#### `fix_video(input_file: str) -> str`
Fix video codec.

**Returns:** Path to fixed video or None

---

## Class 3: ClipVidio

### Constructor
```python
ClipVidio(base_output_dir: str = None, video_id: str = None, output_dir: str = None)
```

### Methods

#### `time_to_seconds(time_str: str) -> int`
Convert time format to seconds.

**Supports:** "SS", "M:SS", "H:MM:SS"

**Returns:** Seconds as integer

---

#### `add_transcripts(video_input: str, use_subtitles: bool = True) -> str`
Add subtitles to video.

**Returns:** FFmpeg filter string

---

#### `clip_video_from_json(video_input: str, use_transcripts: bool = True) -> bool`
Create clips from JSON.

**JSON Format:**
```json
{
  "video_title": "Title",
  "clips": [
    {"start_time": "0:10", "end_time": "0:45", "title": "Clip1"}
  ]
}
```

**Returns:** True if all successful

---

#### `run()`
Interactive menu for clipping.

Displays:
- Available videos
- Subtitle options
- Confirmation before execution
- Progress and results

---

## Class 4: Caption

### Methods

#### `transcribe_clips(video_id: str, model_name: str = 'small', device: str = 'cpu', language: Optional[str] = None, embed: bool = False, overwrite: bool = False, dry_run: bool = False)`
Transcribe clips using Whisper.

**Parameters:**
- `video_id`: Video identifier
- `model_name`: Whisper model (tiny, base, small, medium, large)
- `device`: "cpu" or "cuda"
- `language`: Language code or None (auto-detect)
- `embed`: Embed subtitle into MKV
- `overwrite`: Overwrite existing SRT
- `dry_run`: Test mode with placeholder SRTs

**Returns:** True if successful

---

## Direktori Structure

```
output/
├── raw_assets/{video_id}/
│   ├── transcripts.json          ← Summary JSON
│   ├── transcript.txt            ← Full transcript
│   ├── subtitles.srt             ← Optional
│   ├── video_only.mkv
│   ├── audio_only.mp3
│   ├── temp_video.mkv
│   ├── temp_audio.m4a
│   └── master.mkv
│
└── final_output/{video_id}/
    ├── 01_Intro.mkv
    ├── 01_Intro.srt
    ├── 02_Main.mkv
    ├── 02_Main.srt
    └── ...
```

---

# QUICK_REFERENCE - Cheat Sheet

## Import
```python
from yt_toolkit import Summarize, DownloadVidio, ClipVidio, Caption
```

---

## SUMMARIZE CLASS

```python
summarizer = Summarize(api_key="your_key")

# Get transcript
transcript = summarizer.get_transcript("https://youtube.com/watch?v=ID")

# Summarize
summary = summarizer.summarize(transcript)

# Save
summarizer.save_summary(url, summary, transcript_text=transcript)
```

---

## DOWNLOADVIDIO CLASS

### Quick Start
```python
downloader = DownloadVidio("https://youtube.com/watch?v=ID", video_id="my_video")
```

### Download Options
```python
# Video only
video = downloader.download_video_only()

# Audio only
audio = downloader.download_audio_only()

# Both + remux
video, audio, master = downloader.download_both(remux=True)

# Fix codec
fixed = downloader.fix_video("./raw_assets/master.mkv")

# Remux manual
downloader.remux_video_audio("video.mkv", "audio.m4a", "output.mkv")
```

---

## CLIPVIDIO CLASS

### Quick Start
```python
clipper = ClipVidio(video_id="my_video")
```

### Usage
```python
# Menu interactiv
clipper.run()

# Programmatic
success = clipper.clip_video_from_json(
    video_input="./raw_assets/my_video/master.mkv",
    use_transcripts=True
)

# Time conversion
sec = clipper.time_to_seconds("1:30:45")
```

---

## CAPTION CLASS

```python
caption = Caption()

# Transcribe with Whisper (small model, CPU)
caption.transcribe_clips(video_id="my_video", model_name="small", device="cpu")

# Transcribe and embed
caption.transcribe_clips(video_id="my_video", embed=True)

# Dry run (test without Whisper)
caption.transcribe_clips(video_id="my_video", dry_run=True)

# Custom options
caption.transcribe_clips(
    video_id="my_video",
    model_name="medium",
    device="cuda",
    language="en",
    embed=True,
    overwrite=True
)
```

---

## JSON Format untuk Clips

```json
{
  "video_title": "My Video Title",
  "clips": [
    {
      "start_time": "0:10",
      "end_time": "0:45",
      "title": "Intro"
    },
    {
      "start_time": "1:00",
      "end_time": "2:30",
      "title": "Main Content"
    },
    {
      "start_time": "2:35",
      "end_time": "3:00",
      "title": "Outro"
    }
  ]
}
```

---

## Common Issues & Solutions

| Problem | Solution |
|---------|----------|
| "ffmpeg not found" | Install FFmpeg, ensure in PATH |
| "JSON not found" | Put transcripts.json in raw_assets/{video_id}/ |
| "Module not found" | pip install -r requirements.txt |
| "API key error" | Create .env with GEMINI_API_KEY |
| "Slow transcription" | Use smaller model (tiny/base) |

---

## Performance Tips

```python
# Faster download with lower quality
# (Edit in yt_toolkit.py: adjust format string)

# Faster clipping
'-crf', '28'  # Lower quality, faster
'-preset', 'ultrafast'  # Fastest encoding

# Faster transcription
model_name='tiny'  # Smallest model
device='cuda'  # Use GPU if available

# Parallel processing
from concurrent.futures import ThreadPoolExecutor

videos = ["url1", "url2", "url3"]
with ThreadPoolExecutor(max_workers=3) as executor:
    results = executor.map(download_video, videos)
```

---

## CLI Usage

```bash
# Summarize
python yt_toolkit.py summarize --url "https://youtube.com/watch?v=ID"

# Download
python yt_toolkit.py download --url "https://youtube.com/watch?v=ID" --video-id myid

# Clip
python yt_toolkit.py clip --video-id myid

# Caption (dry-run)
python yt_toolkit.py caption --video-id myid --dry-run
```

---

# FORMAT_CHANGE_MKV - Output Format Update

## 📝 UPDATE: Format Output Clip Diubah ke MKV

### ✅ Perubahan yang Dilakukan

**Format output clip video diubah dari `.mp4` menjadi `.mkv`**

### Alasan Perubahan:
- ✅ MKV (Matroska) format lebih baik untuk menambah caption/subtitle
- ✅ MKV support multiple subtitle tracks (SSA/ASS, SRT, dll)
- ✅ Lebih fleksibel untuk post-processing
- ✅ Ukuran file comparable dengan MP4, tapi lebih versatile

---

## 📂 Output Structure Sebelum & Sesudah

### SEBELUM:
```
final_output/{video_id}/
├── 01_Intro.mp4          ← MP4 format
├── 02_Main_Content.mp4
└── 03_Outro.mp4
```

### SESUDAH:
```
final_output/{video_id}/
├── 01_Intro.mkv          ← MKV format (baru!)
├── 02_Main_Content.mkv
└── 03_Outro.mkv
```

---

## 🎯 Keuntungan Format MKV

| Fitur | MP4 | MKV |
|-------|-----|-----|
| Subtitle embeding | ✓ | ✓✓ |
| Multiple subtitles | ✗ | ✓ |
| Codec support | Limited | Unlimited |
| Hardware support | ✓ | ✓ (increasing) |
| Post-processing | Limited | Excellent |
| Caption format support | SRT | SRT, ASS, SSA, WebVTT |

---

## 📊 Spesifikasi MKV Output

| Property | Value |
|----------|-------|
| Container | Matroska (MKV) |
| Video Codec | H.264 (libx264) |
| Video Bitrate | CRF 18 (high quality) |
| Audio Codec | AAC |
| Audio Bitrate | Auto (best available) |
| Subtitle Support | Yes (multiple tracks) |
| File Size | Similar to MP4 or smaller |

---

## ✅ Compatibility

### Playback Support:
- ✅ VLC Media Player (semua OS)
- ✅ MPC-BE / MPC-HC (Windows)
- ✅ Potplayer (Windows)
- ✅ FFmpeg (untuk re-encoding)
- ✅ HandBrake (untuk convert)

### OS Support:
- ✅ Windows 7+ (dengan player yang tepat)
- ✅ macOS (dengan VLC)
- ✅ Linux (native support)

---

## 🔧 Jika Ingin Kembali ke MP4

Edit `yt_toolkit.py` di class ClipVidio:

```python
# Change from:
output_file = os.path.join(self.final_dir, f"{i:02d}_{clean_label}.mkv")

# To:
output_file = os.path.join(self.final_dir, f"{i:02d}_{clean_label}.mp4")

# Then remove the line:
'-max_muxing_queue_size', '9999',
```

---

## 💾 Storage Konsultasi

Perubahan ini tidak mempengaruhi ukuran file secara signifikan:
- MP4 (libx264, CRF 18): ~100-500 MB per jam
- MKV (libx264, CRF 18): ~100-500 MB per jam

Ukuran hampir identik, hanya container format yang berbeda.

---

---

# GUIDE_ADD_CAPTIONS - Caption Workflow

## 🎬 Panduan: Cara Menambah Caption ke MKV Clips

Setelah generate clips dalam format MKV, Anda bisa menambah caption dengan beberapa cara.

---

## 🛠️ Cara 1: MKVToolNix (GUI - Recommended untuk Pemula)

### Step 1: Download & Install
1. Buka: https://www.bunkus.org/videotools/mkvtoolnix/
2. Download versi sesuai OS Anda (Windows, Mac, Linux)
3. Install seperti program biasa

### Step 2: Embed Caption
```
1. Buka MKVToolNix
2. Klik "Add source files" → Pilih 01_Intro.mkv
3. Di panel "Tracks" → Klik "Add attachments"
4. Pilih file subtitle (*.srt, *.ass, *.ssa)
5. Klik "Multiplex!" → Tunggu selesai
6. Output: 01_Intro-edited.mkv (dengan caption embedded)
```

---

## ⌨️ Cara 2: FFmpeg (Command Line)

### Untuk SRT Subtitle:
```bash
ffmpeg -i 01_Intro.mkv -i captions.srt -c copy -c:s mov_text output.mkv
```

### Untuk ASS/SSA Subtitle:
```bash
ffmpeg -i 01_Intro.mkv -i captions.ass -c copy output.mkv
```

### Batch: Semua file sekaligus
```bash
# Windows Batch Script
for %%f in (*.mkv) do (
    ffmpeg -i "%%f" -i "captions.srt" -c copy -c:s mov_text "%%~nf-with-sub.mkv"
)
```

### Python Script (untuk automation):
```python
import subprocess

def add_subtitle_to_mkv(video_file, subtitle_file, output_file=None):
    """Add subtitle ke MKV file"""
    if output_file is None:
        output_file = video_file.replace('.mkv', '_with_sub.mkv')
    
    cmd = [
        'ffmpeg', '-i', video_file,
        '-i', subtitle_file,
        '-c', 'copy',
        '-c:s', 'mov_text',
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Subtitle added: {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        return None

# Usage:
add_subtitle_to_mkv('01_Intro.mkv', 'captions.srt')
```

---

## 🎥 Cara 3: VLC Media Player (Playback Only)

Tidak embed subtitle, tapi load saat playback:

```
1. Buka VLC Media Player
2. Buka file: 01_Intro.mkv
3. Menu → Subtitle → Open/Load
4. Pilih file .srt atau .ass
5. Subtitle tampil saat playback
```

**Kelebihan:** Tidak perlu re-encode, cepat
**Kekurangan:** Subtitle tidak permanent, hanya saat playback

---

## 📋 Format Subtitle yang Didukung

### SRT (SubRip)
```
1
00:00:00,000 --> 00:00:05,000
Ini adalah subtitle pertama

2
00:00:05,000 --> 00:00:10,000
Ini adalah subtitle kedua
```

### ASS/SSA (Advanced SubStation Alpha)
```
[Script Info]
Title: My Subs
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, Text
Dialogue: 0,0:00:00.00,0:00:05.00,Default,,Ini subtitle pertama
```

---

## 🎯 Workflow Lengkap: Download → Clip → Add Caption

```python
from yt_toolkit import DownloadVidio, ClipVidio, Caption
import subprocess

# Step 1: Download
url = "https://youtube.com/watch?v=ID"
downloader = DownloadVidio(url, video_id="demo")
_, _, master = downloader.download_both(remux=True)

# Step 2: Clip (output: MKV)
clipper = ClipVidio(video_id="demo")
clipper.run()  # Generate 01_Intro.mkv, 02_Main.mkv, dst

# Step 3: Transcribe & embed (automatic captions)
caption = Caption()
caption.transcribe_clips(video_id="demo", model_name="small", embed=True)

print("✅ All done with captions!")
```

---

## 💡 Tips & Tricks

### Tip 1: Sync Subtitle jika Tidak Cocok
```bash
# Delay subtitle +2 detik
ffmpeg -i input.mkv -i subtitle.srt -itsoffset 2 -i subtitle.srt \
    -c copy -c:s mov_text -map 0 -map 1 output.mkv
```

### Tip 2: Multiple Subtitle Tracks
```bash
# Add 2 subtitle tracks (English + Indonesia)
ffmpeg -i video.mkv -i eng_sub.srt -i ind_sub.srt \
    -c copy -c:s mov_text output.mkv
```

### Tip 3: Hardcode Subtitle (Burn into video)
```bash
# Embed subtitle sebagai bagian dari video (tidak bisa dihilangkan)
ffmpeg -i video.mkv -vf subtitles=subtitle.srt \
    -c:a copy output.mkv
```

---

## ⚡ Quick Commands

```bash
# Add SRT subtitle
ffmpeg -i 01_Intro.mkv -i sub.srt -c copy -c:s mov_text output.mkv

# Add ASS subtitle
ffmpeg -i 01_Intro.mkv -i sub.ass -c copy output.mkv

# Convert MKV ke MP4 (jika perlu)
ffmpeg -i 01_Intro.mkv -c copy output.mp4

# Check subtitle tracks dalam MKV
ffprobe 01_Intro.mkv

# Extract subtitle dari MKV
ffmpeg -i 01_Intro.mkv -c copy subtitle_extracted.srt
```

---

## 🎓 Tool Rekomendasi

| Tool | Platform | Tujuan | Mudah? |
|------|----------|--------|--------|
| **MKVToolNix** | Windows/Mac/Linux | GUI multiplex | ✅✅✅ |
| **FFmpeg** | Semua | Command line | ⚠️ (butuh CLI) |
| **Subtitle Edit** | Windows | Edit subtitle | ✅✅ |
| **VLC** | Semua | Playback + load | ✅✅✅ |

---

---

# CAPTIONS_USAGE - Whisper Transcription

## Usage: generate_captions.py (Whisper ASR)

Quick examples to generate captions for clips produced by `ClipVidio`.

### Prerequisites:
- `python` (3.8+)
- `pip install -r requirements.txt` (includes `openai-whisper`)
- `ffmpeg` available (bundled as `ffmpeg.exe` in repo)

### Basic dry-run (no Whisper required, creates placeholder .srt files):
```bash
python yt_toolkit.py caption --video-id testvideo --dry-run
```

### Transcribe with Whisper (small model, CPU):
```bash
python yt_toolkit.py caption --video-id my_video
```

### Transcribe and embed subtitles into MKV:
```bash
python -c "
from yt_toolkit import Caption
caption = Caption()
caption.transcribe_clips('my_video', model_name='small', embed=True)
"
```

### Via Python:
```python
from yt_toolkit import Caption

caption = Caption()

# Basic transcription (small model, CPU)
caption.transcribe_clips(video_id="my_video")

# With embedding
caption.transcribe_clips(video_id="my_video", embed=True)

# Custom options
caption.transcribe_clips(
    video_id="my_video",
    model_name="medium",
    device="cuda",
    language="en",
    embed=True,
    overwrite=True
)

# Dry-run test
caption.transcribe_clips(video_id="my_video", dry_run=True)
```

### Options:
- `video_id`: folder under `output/final_output/{video-id}` containing clips
- `model_name`: whisper model (`tiny`, `base`, `small`, `medium`, `large`)
- `device`: `cpu` or `cuda`
- `embed`: embed generated SRT into MKV (requires ffmpeg)
- `dry_run`: simulate transcription, create placeholder SRT files
- `language`: language code or None (auto-detect)
- `overwrite`: overwrite existing SRT files

### Tips:
- For faster/inferior transcriptions use `tiny` or `base` models
- For best quality use `medium` or `large` (slow, more RAM)
- Use `dry_run=True` first to test without installing large models
- GPU support significantly faster if CUDA available (`device='cuda'`)

---

---

## 🎉 END OF DOCUMENTATION

**This comprehensive guide covers all features of the YT Downloader toolkit.**

For quick reference, start with [GETTING_STARTED](#getting_started---quick-start-guide) or [QUICK_REFERENCE](#quick_reference---cheat-sheet).

Last Updated: January 11, 2026  
Status: ✅ Complete & Ready
