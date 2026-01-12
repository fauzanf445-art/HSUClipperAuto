"""YT Toolkit - merged module

Contains four classes:
 - `Summarize` : fetch & summarize transcript (Gemini / YouTubeTranscriptApi)
 - `DownloadVidio` : download video/audio using yt_dlp
 - `ClipVidio` : create clips from master video using transcripts.json
 - `Caption` : transcribe clips using Whisper and write/embed SRT

Also provides a simple CLI for common tasks.
"""
import cmd
import os
import re
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

# Optional heavy deps
try:
    import yt_dlp
except Exception:
    yt_dlp = None

try:
    import whisper
except Exception:
    whisper = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:
    YouTubeTranscriptApi = None

try:
    from google import genai
except Exception:
    genai = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Summarize:
    """Extract transcript and summarize using Gemini (Google GenAI).

    Minimal wrapper around `youtube_summarizer.py` logic.
    """
    def __init__(self, api_key: Optional[str] = None, model: str = 'gemini-flash-latest', out_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise RuntimeError('Gemini API key not provided. Set GEMINI_API_KEY in .env or pass api_key.')
        if genai is None:
            raise RuntimeError('google-genai package not available')
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        self.out_dir = out_dir or os.path.join(base_dir, 'output', 'raw_assets')
        os.makedirs(self.out_dir, exist_ok=True)

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        m = re.search(regex, url)
        return m.group(1) if m else None

    def get_transcript(self, video_url: str, prefer_langs=('id', 'en')) -> str:
        if YouTubeTranscriptApi is None:
            raise RuntimeError('youtube-transcript-api not installed')
        video_id = self.extract_video_id(video_url)
        if not video_id:
            raise ValueError('Invalid YouTube URL or video id not found.')
        last_exc = None
        for lang in prefer_langs:
            try:
                result = YouTubeTranscriptApi().fetch(video_id, languages=[lang])
                raw = result.to_raw_data()
                full_text = ' '.join([item['text'] for item in raw])
                return full_text
            except Exception as e:
                last_exc = e
                continue
        raise RuntimeError(f'Failed to fetch transcript. Detail: {last_exc}')

    def summarize(self, transcript_text: str, video_url: str) -> str:
        prompt = f"""
        Analisis vidio YouTube berikut berdasarkan URL dan Transcript untuk mencari momen-momen paling penting, menarik (viral-worthy) dan paling penting ada unsur pembelajaran (edukatif).
        
        URL: 
        {video_url}
        Transcript: 
        {transcript_text}
        
        Tugas Anda:
        1) Identifikasi momen yang memiliki dampak emosional tinggi, informasi mengejutkan, atau inti dari argumen pembicara.
        2) Buat "Hook" atau judul klip yang sangat menarik (clicky) namun tetap akurat dalam Bahasa Indonesia.
        3) Pastikan setiap klip memiliki durasi yang ideal untuk video pendek (sekitar 30-90 detik).
        4) Hindari bagian basa-basi seperti intro musik atau ajakan subscribe di awal.

        Persyaratan Format JSON:
        - Key utama: "video_title" dan "clips".
        - Setiap item dalam "clips" wajib memiliki: "title", "start_time", "end_time", "description".
        - Format waktu: HH:MM:SS.

        Output JSON:
        """.strip()

        response = self.client.models.generate_content(
            model=self.model, 
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
            }
        )
        logging.debug('Gemini raw response (first 500 chars): %s', response.text[:500])
        return response.text

    def save_summary(self, video_url: str, summary_text: str, prefix: str = 'summary', transcript_text: Optional[str] = None) -> str:     
        # 1. Ekstrak video ID
        video_id = self.extract_video_id(video_url) or 'unknown'
        
        clean_json = summary_text.strip()
        if clean_json.startswith("```"):
            # Teknik splicing untuk membuang baris pertama (```json) dan terakhir (```)
            lines = clean_json.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_json = "\n".join(lines).strip()

        # 2. Parsing String ke Dictionary
        try:
            parsed = json.loads(clean_json)
            logging.info(f'Sukses memproses JSON untuk video: {video_id}')
        except Exception as e:
            logging.error(f"Gagal parse JSON: {e}")
            # Jika gagal, simpan apa adanya dalam key 'raw' agar program tidak crash
            parsed = {'video_title': 'Unknown', 'clips': [], 'raw_error': summary_text}

        # 3. Tentukan Folder Output
        raw_dir = os.path.join(self.out_dir, video_id)
        os.makedirs(raw_dir, exist_ok=True)
        
        # 4. Simpan sebagai file instruksi untuk ClipVidio
        clips_path = os.path.join(raw_dir, 'transcripts.json')
        with open(clips_path, 'w', encoding='utf-8') as cf:
            json.dump(parsed, cf, ensure_ascii=False, indent=2)
            
        # 5. Simpan transkrip asli (opsional) untuk referensi manual
        if transcript_text:
            with open(os.path.join(raw_dir, 'transcript.txt'), 'w', encoding='utf-8') as tf:
                tf.write(transcript_text)
                
        return clips_path


class DownloadVidio:
    """Downloader class (from video_clipper.py Downloader)
    Methods: download_video_only, download_audio_only, download_both, remux_video_audio, fix_video
    """
    def __init__(self, url: str, base_output_dir: str = None, video_id: str = None):
        self.url = url
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = base_output_dir or os.path.join(base_dir, 'output')
        if not video_id:
            self.video_id = Summarize.extract_video_id(url) or 'unknown_video'
        else:
            self.video_id = video_id
        self.raw_dir = os.path.join(self.base_output_dir, 'raw_assets', self.video_id)
        local_ffmpeg = os.path.join(base_dir, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        self.ffmpeg_path = local_ffmpeg if os.path.exists(local_ffmpeg) else 'ffmpeg'
        local_deno = os.path.join(base_dir, 'deno.exe' if os.name == 'nt' else 'deno')
        self.deno_path = local_deno if os.path.exists(local_deno) else 'deno'
        os.makedirs(self.raw_dir, exist_ok=True)

    def download_video_only(self) -> str:
        logging.info('Downloading video only...')
        output_file = os.path.join(self.raw_dir, 'video_only.mkv')
        opts = {
            'format': 'bestvideo',
            'outtmpl': output_file,
            'ffmpeg_location': self.ffmpeg_path,
            'remote_components': True,
            'remote_components': ['ejs:github', 'ejs:npm'], 
            'update_remote_components': True,            
            'js_runtimes': {
                'deno': {
                    'path': self.deno_path
                }
            },  
            'noplaylist': True,
            'quiet': False,
            'restrictfilenames': True,
            'nocheckcertificate': True,
        }
        if yt_dlp is None:
            logging.error('yt_dlp not installed')
            return None
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            logging.info('Video downloaded successfully: %s', output_file)
            return output_file
        except Exception as e:
            logging.error('Download video failed: %s', e)
            return None

    def download_audio_only(self) -> str:
        logging.info('Downloading audio only...')
        output_file = os.path.join(self.raw_dir, 'audio_only.mp3')
        opts = {
            'format': 'bestaudio',
            'outtmpl': output_file,
            'ffmpeg_location': self.ffmpeg_path,
            'remote_components': True,
            'remote_components': ['ejs:github', 'ejs:npm'], 
            'update_remote_components': True,            
            'js_runtimes': {
                'deno': {
                    'path': self.deno_path
                }
            }, 
            'noplaylist': True,
            'quiet': False,
            'restrictfilenames': True,
            'nocheckcertificate': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        if yt_dlp is None:
            logging.error('yt_dlp not installed')
            return None
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            logging.info('Audio downloaded successfully: %s', output_file)
            return output_file
        except Exception as e:
            logging.error('Download audio failed: %s', e)
            return None

    def download_both(self, remux: bool = True) -> tuple:
        logging.info('Downloading video and audio...')
        video_file = os.path.join(self.raw_dir, 'temp_video.mkv')
        audio_file = os.path.join(self.raw_dir, 'temp_audio.m4a')
        opts_video = {
            'format': 'bestvideo',
            'outtmpl': video_file,
            'ffmpeg_location': self.ffmpeg_path,
            'remote_components': True,
            'remote_components': ['ejs:github', 'ejs:npm'], 
            'update_remote_components': True,            
            'js_runtimes': {
                'deno': {
                    'path': self.deno_path
                }
            },
            'noplaylist': True,
            'quiet': False,
            'restrictfilenames': True,
            'nocheckcertificate': True,
        }
        if yt_dlp is None:
            logging.error('yt_dlp not installed')
            return None, None, None
        try:
            with yt_dlp.YoutubeDL(opts_video) as ydl:
                ydl.download([self.url])
        except Exception as e:
            logging.error('Download video failed: %s', e)
            return None, None, None
        opts_audio = {
            'format': 'bestaudio',
            'outtmpl': audio_file,
            'ffmpeg_location': self.ffmpeg_path,
            'remote_components': True,
            'remote_components': ['ejs:github', 'ejs:npm'], 
            'update_remote_components': True,            
            'js_runtimes': {
                'deno': {
                    'path': self.deno_path
                }
            },
            'noplaylist': True,
            'quiet': False,
            'restrictfilenames': True,
            'nocheckcertificate': True,
        }
        try:
            with yt_dlp.YoutubeDL(opts_audio) as ydl:
                ydl.download([self.url])
        except Exception as e:
            logging.error('Download audio failed: %s', e)
            return None, None, None
        remuxed_file = None
        if remux and os.path.exists(video_file) and os.path.exists(audio_file):
            remuxed_file = os.path.join(self.raw_dir, 'master.mkv')
            if self.remux_video_audio(video_file, audio_file, remuxed_file):
                logging.info('Video and audio remuxed successfully: %s', remuxed_file)
        return video_file, audio_file, remuxed_file

    def remux_video_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            output_path
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except subprocess.CalledProcessError as e:
            logging.error('Remux failed: %s', e.stderr.decode('utf-8', errors='replace'))
            return False

    def fix_video(self, input_file: str) -> str:
        logging.info('Fixing video codec...')
        output_file = os.path.join(self.raw_dir, 'master_fixed.mkv')
        fix_cmd = [
            self.ffmpeg_path, '-y', '-i', input_file,
            '-c', 'copy', '-map_metadata', '0',
            '-movflags', '+faststart', output_file
        ]
        try:
            subprocess.run(fix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info('Video fixed successfully: %s', output_file)
            return output_file
        except subprocess.CalledProcessError as cpe:
            logging.error('Fix video failed: %s', cpe.stderr.decode('utf-8', errors='replace'))
            return None


class ClipVidio:
    """Clip creation class (from VideoClipper)
    Use: provide base_output_dir and video_id; call clip_video_from_json or run() for interactive.
    """
    def __init__(self, base_output_dir: str = None, video_id: str = None, output_dir: str = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = base_output_dir or os.path.join(base_dir, 'output')
        if not video_id:
            self.video_id = Summarize.extract_video_id(url) or 'unknown_video'
        else:
            self.video_id = video_id
        self.raw_dir = os.path.join(self.base_output_dir, 'raw_assets', self.video_id)
        self.final_dir = output_dir or os.path.join(self.base_output_dir, 'final_output', self.video_id)
        self.json_path = os.path.join(self.raw_dir, 'transcripts.json')
        local_ffmpeg = os.path.join(base_dir, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        self.ffmpeg_path = local_ffmpeg if os.path.exists(local_ffmpeg) else 'ffmpeg'   
        for folder in [self.raw_dir, self.final_dir]:
            os.makedirs(folder, exist_ok=True)

    def time_to_seconds(self, time_str: str) -> int:
        if not isinstance(time_str, str):
            raise ValueError('time_str must be a string')
        s = time_str.split('.')[0].strip()
        parts = s.split(':')
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f'Invalid time format: {time_str}')
        if len(parts) == 1:
            h, m, sec = 0, 0, parts[0]
        elif len(parts) == 2:
            h, m, sec = 0, parts[0], parts[1]
        elif len(parts) == 3:
            h, m, sec = parts
        else:
            raise ValueError(f'Unsupported time format: {time_str}')
        return int(h) * 3600 + int(m) * 60 + int(sec)

    def clip_video_from_json(self, video_input: str, use_transcripts: bool = True) -> bool:
        if not os.path.exists(self.json_path):
            logging.error('Transcripts JSON not found at %s', self.json_path)
            return False
        if not os.path.exists(video_input):
            logging.error('Video input not found: %s', video_input)
            return False
        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        clips = data.get('clips', [])
        if not clips:
            logging.error('No clips found in %s', self.json_path)
            return False
        logging.info('Processing %d clips from JSON...', len(clips))
        success_count = 0
        for i, item in enumerate(clips, 1):
            try:
                start_sec = self.time_to_seconds(item['start_time'])
                end_sec = self.time_to_seconds(item['end_time'])
                duration = end_sec - start_sec
                title = item.get('title', f'clip_{i}')
                clean_label = "".join([c for c in title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
                output_file = os.path.join(self.final_dir, f"{i:02d}_{clean_label}.mkv")
                cmd = [
                    self.ffmpeg_path, '-y',
                    '-i', video_input,
                    '-ss', str(start_sec),
                    '-t', str(duration),
                    '-vf', 'setsar=1',
                    '-c:v', 'libx264',
                    '-crf', '18',
                    '-preset', 'ultrafast',
                    '-c:a', 'aac',
                    '-avoid_negative_ts', 'make_zero',
                    '-max_muxing_queue_size', '9999',
                    output_file
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info('✓ Clip %d done: %s (%d sec)', i, os.path.basename(output_file), duration)
                success_count += 1
            except subprocess.CalledProcessError as cpe:
                logging.error('✗ ffmpeg failed for clip %d: %s', i, cpe.stderr.decode('utf-8', errors='replace'))
            except Exception as e:
                logging.error('✗ Error processing clip %d: %s', i, e)
        logging.info('Completed: %d/%d clips created successfully!', success_count, len(clips))
        return success_count == len(clips)

    def run(self):
        print('\n' + '='*60)
        print('🎬 VIDEO CLIPPER - Interactive Menu')
        print('='*60)
        if not os.path.exists(self.json_path):
            logging.error('Transcripts JSON not found at %s', self.json_path)
            print(f"❌ JSON file not found: {self.json_path}")
            return False
        master_video = os.path.join(self.raw_dir, 'master.mkv')
        master_fixed = os.path.join(self.raw_dir, 'master_fixed.mkv')
        video_input = None
        if os.path.exists(master_fixed):
            video_input = master_fixed
        elif os.path.exists(master_video):
            video_input = master_video
        else:
            available_videos = [f for f in os.listdir(self.raw_dir) if f.endswith(('.mkv', '.mp4', '.mov'))]
            if available_videos:
                print(f"\n✓ Available videos in {self.raw_dir}:")
                for idx, vid in enumerate(available_videos, 1):
                    print(f"  {idx}. {vid}")
                choice = input("\nSelect video (number or leave empty for first): ").strip()
                if choice.isdigit() and 1 <= int(choice) <= len(available_videos):
                    video_input = os.path.join(self.raw_dir, available_videos[int(choice)-1])
                else:
                    video_input = os.path.join(self.raw_dir, available_videos[0])
            else:
                logging.error('No master video found in %s', self.raw_dir)
                print(f"❌ No video files found in {self.raw_dir}")
                return False
        print(f"\n📹 Video: {os.path.basename(video_input)}")
        print(f"📝 JSON:  {os.path.basename(self.json_path)}")
        print("\n" + "-"*60)
        print("Summary:")
        print(f"  Video input: {video_input}")
        print(f"  Output dir: {self.final_dir}")
        print("-"*60)
        confirm = input("\n▶️  Proceed with clipping? (yes/no): ").strip().lower()
        if confirm not in ('yes', 'y'):
            print("❌ Cancelled")
            return False
        print("\n⏳ Processing clips...\n")
        success = self.clip_video_from_json(video_input, use_transcripts=False)
        if success:
            print(f"\n✅ All clips completed successfully!")
            print(f"📁 Output saved to: {self.final_dir}")
        else:
            print(f"\n⚠️  Some clips failed. Check logs for details.")
        return success


class Caption:
    """Captioning class (wraps generate_captions.py logic using Whisper)
    Methods: transcribe_clips(video_id, model, device, language, embed, overwrite, dry_run)
    """
    def __init__(self, base_output_dir: str = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = base_output_dir or os.path.join(base_dir, 'output')
        local_ffmpeg = os.path.join(base_dir, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        self.ffmpeg_path = local_ffmpeg if os.path.exists(local_ffmpeg) else 'ffmpeg'

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _write_srt(segments, srt_path: Path):
        with srt_path.open('w', encoding='utf-8') as fh:
            for i, seg in enumerate(segments, start=1):
                start = Caption._format_timestamp_srt(seg['start'])
                end = Caption._format_timestamp_srt(seg['end'])
                text = seg['text'].strip()
                fh.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    def _find_clips(self, video_id: str):
        clips_dir = Path(self.base_output_dir) / 'final_output' / video_id
        if not clips_dir.exists():
            return []
        return sorted([p for p in clips_dir.iterdir() if p.suffix.lower() in ('.mkv', '.mp4', '.mov')])

    def transcribe_clips(self, video_id: str, model_name: str = 'small', device: str = 'cpu', language: Optional[str] = None, embed: bool = False, overwrite: bool = False, dry_run: bool = False):
        clips = self._find_clips(video_id)
        if not clips:
            logging.error('No clips found for video_id=%s', video_id)
            return False
        if dry_run:
            model = None
            print('Dry-run mode: creating placeholder SRTs')
        else:
            if whisper is None:
                logging.error('Whisper not installed')
                return False
            print(f'Loading Whisper model {model_name} on {device}...')
            model = whisper.load_model(model_name, device=device)
        for clip in clips:
            print('Processing', clip.name)
            srt_path = clip.with_suffix('.srt')
            if srt_path.exists() and not overwrite:
                print(' SRT exists, skip (use overwrite)')
                continue
            if dry_run:
                segments = [{'start': 0.0, 'end': 1.0, 'text': '[DRY-RUN] placeholder'}]
            else:
                res = model.transcribe(str(clip), language=language) if model else None
                segments = []
                if res and 'segments' in res:
                    for s in res['segments']:
                        segments.append({'start': s['start'], 'end': s['end'], 'text': s['text']})
            Caption._write_srt(segments, srt_path)
            print(' Written', srt_path.name)
            if embed:
                out = self._embed_srt(clip, srt_path, overwrite=overwrite)
                if out:
                    print(' Embedded ->', out.name)
        return True

    def _embed_srt(self, video_path: Path, srt_path: Path, overwrite: bool = True):
        temp_output = video_path.parent / f"temp_{video_path.name}"

        cmd = [
            self.ffmpeg_path, '-y',
            '-i', str(video_path),
            '-i', str(srt_path),
            '-c', 'copy',
            '-c:s', 'mov_text', # Format subtitle standar untuk MP4/MKV
            str(temp_output)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            
            # JIKA BERHASIL: Hapus file video lama dan file SRT
            if temp_output.exists():
                video_path.unlink()   # Hapus file asli tanpa subtitle
                srt_path.unlink()     # Hapus file SRT (karena sudah masuk ke dalam video)
                
                # Ganti nama file temp menjadi nama file asli
                temp_output.rename(video_path) 
                return video_path
                
        except subprocess.CalledProcessError as e:
                logging.error(f"Gagal embedding: {e}")
                if temp_output.exists():
                    temp_output.unlink()
                return None


def _cli():
    import argparse
    parser = argparse.ArgumentParser(description='YT Toolkit CLI')
    sub = parser.add_subparsers(dest='cmd')
    # Summarize
    p_sum = sub.add_parser('summarize')
    p_sum.add_argument('--url', required=True)
    p_sum.add_argument('--api-key', required=False)
    # Download
    p_dl = sub.add_parser('download')
    p_dl.add_argument('--url', required=True)
    p_dl.add_argument('--video-id', required=False)
    p_dl.add_argument('--both', action='store_true')
    # Clip
    p_clip = sub.add_parser('clip')
    p_clip.add_argument('--video-id', required=True)
    # Caption
    p_cap = sub.add_parser('caption')
    p_cap.add_argument('--video-id', required=True)
    p_cap.add_argument('--dry-run', action='store_true')
    # Merge clips + captions
    p_merge = sub.add_parser('merge')
    p_merge.add_argument('--video-id', required=True)
    p_merge.add_argument('--model', default='small')
    p_merge.add_argument('--device', default='cpu')
    p_merge.add_argument('--language', required=False)
    p_merge.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.cmd == 'summarize':
        s = Summarize(api_key=args.api_key)
        transcript = s.get_transcript(args.url)
        summary = s.summarize(transcript)
        s.save_summary(args.url, summary, transcript_text=transcript)
    elif args.cmd == 'download':
        d = DownloadVidio(args.url, video_id=args.video_id)
        if args.both:
            d.download_both(remux=True)
        else:
            d.download_video_only()
    elif args.cmd == 'clip':
        c = ClipVidio(video_id=args.video_id)
        c.run()
    elif args.cmd == 'caption':
        cap = Caption()
        cap.transcribe_clips(args.video_id, dry_run=args.dry_run)
    elif args.cmd == 'merge':
        print(f"\n{'='*60}")
        print('🎬 MERGE CLIPS + CAPTIONS')
        print(f"{'='*60}\n")
        cap = Caption()
        print(f"Step 1: Transcribe clips with Whisper (model={args.model}, device={args.device})")
        cap.transcribe_clips(
            video_id=args.video_id,
            model_name=args.model,
            device=args.device,
            language=args.language,
            embed=True,
            dry_run=args.dry_run
        )
        print(f"\n✅ Clips with embedded captions created!")
        print(f"📁 Output: output/final_output/{args.video_id}/\n")
    else:
        parser.print_help()


if __name__ == '__main__':
    _cli()
