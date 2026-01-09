import os
import sys
import logging
from youtube_summarizer import YouTubeSummarizer
from video_clipper import VideoClipper

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_ROOT = os.path.join(BASE, 'raw_assets')
FINAL_ROOT = os.path.join(BASE, 'final_output')

def prepare_video_dirs(video_id: str):
    # Clipper Anda mencari file di: raw_assets/{video_id}/transcripts.json
    # Summary JSON juga disimpan di raw_assets/{video_id}/
    dirs = {
        "video_raw": os.path.join(RAW_ROOT, video_id),
        "video_final": os.path.join(FINAL_ROOT, video_id)
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs

def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    logging.info('=== Workflow Orchestrator ===')
    url = input("Enter YouTube URL: ").strip()
    if not url: sys.exit(1)

    video_id = YouTubeSummarizer.extract_video_id(url)
    if not video_id:
        print("Invalid URL"); sys.exit(1)

    paths = prepare_video_dirs(video_id)

    # 1) Summarize - Output JSON akan ditaruh di raw_assets
    logging.info('-- Step 1: Summarize transcript --')
    try:
        summarizer = YouTubeSummarizer(out_dir=paths['video_raw'])
    except Exception as e:
        logging.error('Summarizer initialization failed: %s', e)
        logging.error('Ensure GEMINI_API_KEY is set in .env or passed to YouTubeSummarizer')
        sys.exit(1)

    try:
        summarizer.summarize_video(url)
    except Exception as e:
        logging.error('Summarization failed: %s', e)

    # 2) Download and Clip - Menggunakan class asli tanpa ubah code
    print("\n-- Step 2: Download and Generate clips --")
    # Clipper asli Anda menggunakan urutan: (url, base_output_dir, video_id)
    clipper = VideoClipper(url, base_output_dir=BASE, video_id=video_id)
    try:
        clipper.run()
    except Exception as e:
        print(f"Clipper failed: {e}")

if __name__ == '__main__':
    main()