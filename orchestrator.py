#!/usr/bin/env python
"""
YT Toolkit Orchestrator - Complete Workflow

Demonstrates the full workflow:
  1. Download video from YouTube
  2. Summarize & extract clips using Gemini
  3. Create clips from master video
  4. Transcribe clips & embed captions
"""

import os
import sys
import logging
from pathlib import Path

from yt_toolkit import Summarize, DownloadVidio, ClipVidio, Caption


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def print_header(title: str):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_menu():
    """Display main menu"""
    print("\n" + "="*70)
    print("  YT TOOLKIT - ORCHESTRATOR")
    print("="*70)
    print("\nAvailable Options:")
    print("  1. Full Workflow (Download → Summarize → Clip → Caption)")
    print("  2. Download Only")
    print("  3. Summarize Only")
    print("  4. Clip Only (from existing JSON)")
    print("  5. Caption Only (from existing clips)")
    print("  6. Embed Captions (Transcribe + Burn-in Subtitles)")
    print("  7. Exit")
    print("\n" + "="*70)
    choice = input("\nSelect option (1-7): ").strip()
    return choice


def workflow_download(url: str, video_id: str):
    """Download video from YouTube"""
    print_header(f"🎥 STEP 1: DOWNLOAD VIDEO")
    
    try:
        downloader = DownloadVidio(url, video_id=video_id)
        print(f"URL: {url}")
        print(f"Video ID: {video_id}\n")
        
        print("Download options:")
        print("  1. Video Only")
        print("  2. Audio Only")
        print("  3. Video + Audio (Remux)")
        
        choice = input("\nSelect (1-3): ").strip()
        
        if choice == "1":
            print("\n⏳ Downloading video only...")
            result = downloader.download_video_only()
            print(f"✅ Video: {result}")
            return result
        elif choice == "2":
            print("\n⏳ Downloading audio only...")
            result = downloader.download_audio_only()
            print(f"✅ Audio: {result}")
            return result
        elif choice == "3":
            print("\n⏳ Downloading video + audio...")
            video, audio, master = downloader.download_both(remux=True)
            print(f"✅ Video: {video}")
            print(f"✅ Audio: {audio}")
            print(f"✅ Master (Remuxed): {master}")
            return master
        else:
            print("❌ Invalid choice")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def workflow_summarize(url: str, video_id: str, api_key: str = None):
    """Summarize video & extract clips"""
    print_header(f"📝 STEP 2: SUMMARIZE VIDEO")
    
    try:
        summarizer = Summarize(api_key=api_key)
        
        print(f"URL: {url}")
        print(f"Video ID: {video_id}\n")
        
        print("⏳ Fetching transcript...")
        transcript = summarizer.get_transcript(url, prefer_langs=('en', 'id'))
        print(f"✅ Transcript fetched ({len(transcript)} chars)\n")
        
        print("⏳ Summarizing with Gemini...")
        summary = summarizer.summarize(transcript)
        print(f"✅ Summary generated\n")
        
        print("⏳ Saving summary & clips...")
        clips_path = summarizer.save_summary(url, summary, transcript_text=transcript)
        print(f"✅ Clips saved: {clips_path}\n")
        
        # Display extracted clips
        import json
        with open(clips_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict) and data.get('clips'):
            print("Extracted Clips:")
            for i, clip in enumerate(data['clips'], 1):
                print(f"  {i}. {clip.get('title', 'Untitled')} ({clip.get('start_time', '?')} - {clip.get('end_time', '?')})")
        
        return clips_path
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def workflow_clip(video_id: str, master_video: str = None):
    """Create clips from master video"""
    print_header(f"✂️  STEP 3: CREATE CLIPS")
    
    try:
        clipper = ClipVidio(video_id=video_id)
        
        # If no master video provided, try to find it
        if not master_video:
            master_video = os.path.join(clipper.raw_dir, 'master.mkv')
            if not os.path.exists(master_video):
                print(f"❌ Master video not found: {master_video}")
                return False
        
        print(f"Video ID: {video_id}")
        print(f"Master: {master_video}\n")
        
        # Check if JSON exists
        if not os.path.exists(clipper.json_path):
            print(f"❌ Clips JSON not found: {clipper.json_path}")
            print("   Make sure to run 'Summarize' first or manually create transcripts.json")
            return False
        
        print("⏳ Creating clips from JSON...")
        success = clipper.clip_video_from_json(master_video, use_transcripts=False)
        
        if success:
            print(f"✅ All clips created successfully!")
            print(f"📁 Output: {clipper.final_dir}")
            return True
        else:
            print(f"⚠️  Some clips may have failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def workflow_caption(video_id: str, model: str = 'small', device: str = 'cpu', dry_run: bool = False):
    """Transcribe & embed captions"""
    print_header(f"📝 STEP 4: ADD CAPTIONS")
    
    try:
        caption = Caption()
        
        print(f"Video ID: {video_id}")
        print(f"Model: {model}")
        print(f"Device: {device}")
        print(f"Dry-run: {dry_run}\n")
        
        print("⏳ Transcribing clips...")
        success = caption.transcribe_clips(
            video_id=video_id,
            model_name=model,
            device=device,
            embed=False,  # Don't embed in this step
            dry_run=dry_run
        )
        
        if success:
            print(f"\n✅ Transcription complete!")
            return True
        else:
            print(f"\n❌ Transcription failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def workflow_merge(video_id: str, model: str = 'small', device: str = 'cpu', dry_run: bool = False):
    """Transcribe and embed captions into existing clips"""
    print_header(f"🎬 EMBED CAPTIONS")
    
    try:
        caption = Caption()
        
        print(f"Video ID: {video_id}")
        print(f"Model: {model}")
        print(f"Device: {device}")
        print(f"Dry-run: {dry_run}\n")
        
        print("⏳ Transcribing & embedding captions...")
        success = caption.transcribe_clips(
            video_id=video_id,
            model_name=model,
            device=device,
            embed=True,  # Embed captions
            dry_run=dry_run
        )
        
        if success:
            print(f"\n✅ Clips with embedded captions created!")
            print(f"📁 Output: output/final_output/{video_id}/")
            return True
        else:
            print(f"\n❌ Process failed")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def full_workflow():
    """Run complete workflow"""
    print_header("🚀 FULL WORKFLOW TEST")
    
    # Input
    url = input("Enter YouTube URL: ").strip()
    video_id = input("Enter Video ID (or leave empty for auto): ").strip()
    
    if not video_id:
        video_id = Summarize.extract_video_id(url)
        if not video_id:
            print("❌ Could not extract video ID from URL")
            return
    
    api_key = input("Enter Gemini API Key (or press Enter to use .env): ").strip()
    
    print(f"\n✅ Configuration:")
    print(f"   URL: {url}")
    print(f"   Video ID: {video_id}")
    print(f"   API Key: {'***' if api_key else 'Using .env'}\n")
    
    confirm = input("Continue with full workflow? (yes/no): ").strip().lower()
    if confirm not in ('yes', 'y'):
        print("❌ Cancelled")
        return
    
    # Step 1: Download
    master = workflow_download(url, video_id)
    if not master:
        print("❌ Download failed. Stopping workflow.")
        return
    
    # Step 2: Summarize
    clips_path = workflow_summarize(url, video_id, api_key=api_key)
    if not clips_path:
        print("❌ Summarize failed. Stopping workflow.")
        return
    
    # Step 3: Clip
    clip_success = workflow_clip(video_id, master)
    if not clip_success:
        print("⚠️  Clipping completed with warnings")
    
    # Step 4: Caption (with embed)
    print_header(f"📝 STEP 4: ADD CAPTIONS (WITH EMBED)")
    
    model = input("Whisper model (tiny/base/small/medium/large) [default: small]: ").strip() or 'small'
    device = input("Device (cpu/cuda) [default: cpu]: ").strip() or 'cpu'
    dry_run_choice = input("Dry-run mode? (yes/no) [default: no]: ").strip().lower()
    dry_run = dry_run_choice in ('yes', 'y')
    
    caption_success = workflow_merge(video_id, model=model, device=device, dry_run=dry_run)
    
    # Summary
    print_header("✅ WORKFLOW COMPLETE")
    print("Results:")
    print(f"  ✓ Download: {'OK' if master else 'FAILED'}")
    print(f"  ✓ Summarize: {'OK' if clips_path else 'FAILED'}")
    print(f"  ✓ Clip: {'OK' if clip_success else 'FAILED'}")
    print(f"  ✓ Caption: {'OK' if caption_success else 'FAILED'}")
    print(f"\n📁 Output: output/final_output/{video_id}/\n")


def test_download_only():
    """Test download functionality"""
    url = input("Enter YouTube URL: ").strip()
    video_id = input("Enter Video ID (or leave empty for auto): ").strip()
    
    if not video_id:
        video_id = Summarize.extract_video_id(url)
    
    workflow_download(url, video_id)


def test_summarize_only():
    """Test summarize functionality"""
    url = input("Enter YouTube URL: ").strip()
    video_id = input("Enter Video ID (or leave empty for auto): ").strip()
    api_key = input("Enter Gemini API Key (or press Enter to use .env): ").strip()
    
    if not video_id:
        video_id = Summarize.extract_video_id(url)
    
    workflow_summarize(url, video_id, api_key=api_key if api_key else None)


def test_clip_only():
    """Test clipping functionality"""
    video_id = input("Enter Video ID: ").strip()
    master = input("Enter path to master video (or leave empty to auto-find): ").strip()
    
    workflow_clip(video_id, master_video=master if master else None)


def test_caption_only():
    """Test caption functionality"""
    video_id = input("Enter Video ID: ").strip()
    model = input("Whisper model (tiny/base/small/medium/large) [default: small]: ").strip() or 'small'
    device = input("Device (cpu/cuda) [default: cpu]: ").strip() or 'cpu'
    dry_run_choice = input("Dry-run mode? (yes/no) [default: no]: ").strip().lower()
    dry_run = dry_run_choice in ('yes', 'y')
    
    workflow_caption(video_id, model=model, device=device, dry_run=dry_run)


def test_merge():
    """Test merge (clip + caption)"""
    video_id = input("Enter Video ID: ").strip()
    model = input("Whisper model (tiny/base/small/medium/large) [default: small]: ").strip() or 'small'
    device = input("Device (cpu/cuda) [default: cpu]: ").strip() or 'cpu'
    dry_run_choice = input("Dry-run mode? (yes/no) [default: no]: ").strip().lower()
    dry_run = dry_run_choice in ('yes', 'y')
    
    workflow_merge(video_id, model=model, device=device, dry_run=dry_run)


def main():
    """Main orchestrator"""
    while True:
        choice = print_menu()
        
        if choice == "1":
            full_workflow()
        elif choice == "2":
            test_download_only()
        elif choice == "3":
            test_summarize_only()
        elif choice == "4":
            test_clip_only()
        elif choice == "5":
            test_caption_only()
        elif choice == "6":
            test_merge()
        elif choice == "7":
            print("\n✅ Goodbye!\n")
            sys.exit(0)
        else:
            print("❌ Invalid option. Please try again.")
        
        input("\n\nPress Enter to continue...")


if __name__ == '__main__':
    main()
