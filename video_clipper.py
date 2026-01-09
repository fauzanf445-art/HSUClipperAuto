import yt_dlp
import os
import json
import subprocess
import logging
from datetime import datetime

class VideoClipper:
    """Create clips from a master video using segments described in JSON.

    The JSON is expected at: raw_assets/{video_id}/transcripts.json or final_output/{video_id}/transcripts.json
    and should contain a top-level "clips" list with objects having "start_time" and "end_time" in HH:MM:SS.
    """

    def __init__(self, url: str, base_output_dir: str = None, video_id: str = None, output_dir: str = None):
        self.url = url
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = base_output_dir or os.path.join(base_dir, 'output')
        
        # JIKA video_id tidak diberikan, kita coba ambil ID dari URL YouTube
        if not video_id and "v=" in url:
            # Mengambil string setelah 'v=' (contoh: dQw4w9WgXcQ)
            self.video_id = url.split("v=")[1].split("&")[0]
        else:
            self.video_id = video_id

        # Sekarang, baik video_id diberikan manual atau auto-detect, 
        # kita pakai struktur folder yang sama (raw_assets)
        if self.video_id:
            self.raw_dir = os.path.join(self.base_output_dir, 'raw_assets', self.video_id)
            self.final_dir = output_dir or os.path.join(self.base_output_dir, 'final_output', self.video_id)
            self.json_path = os.path.join(self.raw_dir, 'transcripts.json')
            self.srt_path = os.path.join(self.raw_dir, 'subtitles.srt')
        else:
            # Fallback terakhir jika ID benar-benar tidak ditemukan (misal bukan link YT)
            self.raw_dir = os.path.join(self.base_output_dir, 'raw_assets', 'unknown_video')
            self.final_dir = os.path.join(self.base_output_dir, 'final_output', 'unknown_video')
            self.json_path = os.path.join(self.raw_dir, 'transcripts.json')
            self.srt_path = os.path.join(self.raw_dir, 'subtitles.srt')

        self.ffmpeg_path = os.path.join(base_dir, 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        for folder in [self.raw_dir, self.final_dir]:
            os.makedirs(folder, exist_ok=True)

    def time_to_seconds(self, time_str: str) -> int:
        # tolerant parser: supports H:MM:SS, M:SS, SS, and optional fractional seconds
        if not isinstance(time_str, str):
            raise ValueError("time_str must be a string")
        s = time_str.split('.')[0].strip()
        parts = s.split(':')
        try:
            parts = [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}")

        if len(parts) == 1:
            h, m, sec = 0, 0, parts[0]
        elif len(parts) == 2:
            h, m, sec = 0, parts[0], parts[1]
        elif len(parts) == 3:
            h, m, sec = parts
        else:
            raise ValueError(f"Unsupported time format: {time_str}")

        return int(h) * 3600 + int(m) * 60 + int(sec)

    def download_and_fix(self) -> str:
        logging.info('Downloading master video...')
        temp_file = os.path.join(self.raw_dir, 'temp_master.mkv')
        fixed_file = os.path.join(self.raw_dir, 'master_fixed.mkv')

        opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': temp_file,
            'ffmpeg_location': self.ffmpeg_path,
            'merge_output_format': 'mkv',
            'noplaylist': True,
            'quiet': False,
            'restrictfilenames': True,
            'nocheckcertificate': True,
            'remote_components': ['ejs:github'],
            'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mkv'
            }],
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            logging.error('yt-dlp download failed: %s', e)
            return None

        if not os.path.exists(temp_file):
            logging.error('Download completed but temp file not found: %s', temp_file)
            return None

        fix_cmd = [
            self.ffmpeg_path, '-y', '-i', temp_file,
            '-c', 'copy', '-map_metadata', '0',
            '-movflags', '+faststart', fixed_file
        ]
        try:
            subprocess.run(fix_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return fixed_file
        except subprocess.CalledProcessError as cpe:
            logging.error('ffmpeg fix failed: returncode=%s stderr=%s', cpe.returncode, cpe.stderr.decode('utf-8', errors='replace'))
            return None

    def run(self):
        # Check if transcripts.json exists at raw_assets/{video_id}/transcripts.json
        if not os.path.exists(self.json_path):
            logging.error('Transcripts JSON not found at %s', self.json_path)
            return

        video_input = self.download_and_fix()
        if not video_input:
            return

        with open(self.json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # transcripts.json has clips at top level: {"video_title": "...", "clips": [...]}
        clips = data.get('clips', [])
        if not clips:
            logging.error('No clips found in %s', self.json_path)
            return
        logging.info('Processing %d clips from JSON...', len(clips))

        for i, item in enumerate(clips, 1):
            start_sec = self.time_to_seconds(item['start_time'])
            end_sec = self.time_to_seconds(item['end_time'])
            duration = end_sec - start_sec
            title = item.get('title', f'clip_{i}')
            clean_label = "".join([c for c in title if c.isalnum() or c in (' ', '_')]).strip().replace(' ', '_')
            output_file = os.path.join(self.final_dir, f"{i:02d}_{clean_label}.mp4")

            video_filter = 'setsar=1'
            if os.path.exists(self.srt_path):
                safe_srt = self.srt_path.replace('\\', '/').replace(':', '\\:')
                video_filter = f"subtitles='{safe_srt}':force_style='FontSize=20,PrimaryColour=&H00FFFF&'"

            cmd = [
                self.ffmpeg_path, '-y',
                '-i', video_input,
                '-ss', str(start_sec),
                '-t', str(duration),
                '-vf', video_filter,
                '-c:v', 'libx264',
                '-crf', '18',
                '-preset', 'ultrafast',
                '-c:a', 'aac',
                '-avoid_negative_ts', 'make_zero',
                output_file
            ]

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info('Clip %d done: %s (%d sec)', i, os.path.basename(output_file), duration)
            except subprocess.CalledProcessError as cpe:
                logging.error('ffmpeg failed for clip %d: returncode=%s stderr=%s', i, cpe.returncode, cpe.stderr.decode('utf-8', errors='replace'))
                # continue with next clip

        logging.info('All clips created successfully!')