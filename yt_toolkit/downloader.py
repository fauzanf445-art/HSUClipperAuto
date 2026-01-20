import os
import json
import logging
import re
import subprocess
from typing import Tuple, Optional, List

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

from .summarizer import Summarize

def sanitize_filename(name: str) -> str:
    """Membersihkan string agar menjadi nama file/folder yang valid."""
    # Hapus karakter ilegal
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Ganti spasi dengan strip
    name = name.replace(" ", "-")
    # Batasi panjangnya agar tidak terlalu panjang untuk path Windows
    return name[:70].lower()

class DownloadVidio:
    def __init__(self, url: str, output_dir: str, ffmpeg_path: str, deno_path: str, use_gpu: bool = True, video_id: Optional[str] = None):
        self.url = url
        self.base_output_dir = output_dir
        self.youtube_id = video_id or Summarize.extract_video_id(url) or 'unknown_video'
        self.ffmpeg_path = ffmpeg_path
        self.deno_path = deno_path
        self.use_gpu = use_gpu

        # Properti ini akan diisi oleh setup_directories()
        self.video_title: Optional[str] = None
        self.asset_folder_name: Optional[str] = None
        self.raw_dir: Optional[str] = None

    def setup_directories(self):
        """Mengambil metadata video untuk membuat nama folder yang deskriptif."""
        logging.info("Mengambil judul video untuk penamaan folder...")
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(self.url, download=False)
            self.video_title = info.get('title', 'unknown-title')
        
        sanitized_title = sanitize_filename(self.video_title)
        self.asset_folder_name = f"{sanitized_title}-{self.youtube_id}"
        self.raw_dir = os.path.join(self.base_output_dir, self.asset_folder_name)
        os.makedirs(self.raw_dir, exist_ok=True)
        logging.info(f"Folder aset diatur ke: {self.asset_folder_name}")

    def download_both_separate(self) -> Tuple[Optional[str], Optional[str]]:
        """Mengunduh video dan audio secara terpisah dengan format asli."""
        if yt_dlp is None:
            logging.error("Library 'yt_dlp' tidak ditemukan.")
            return None, None
            
        video_tmpl = os.path.join(self.raw_dir, 'vidio.%(ext)s')
        audio_tmpl = os.path.join(self.raw_dir, 'audio.%(ext)s')

        try:
            video_opts = {
                'format': 'bestvideo/best',
                'outtmpl': video_tmpl,
                'retries': 10,
                'fragment_retries': 10,
                'retry_sleep': 5,
                'continuedl': True,
                'remote_components': ['ejs:github', 'ejs:npm'], 
                'update_remote_components': True,            
                'js_runtimes': {
                    'deno': {
                        'path': self.deno_path
                    }
                },
                'postprocessor_args': [
                '-map_metadata', '-1',
                ],
                
            }

            # 2. Konfigurasi Download Audio (Paksa konversi ke MP3)
            audio_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_tmpl,
                'retries': 10,
                'fragment_retries': 10,
                'retry_sleep': 5,
                'continuedl': True,
                'remote_components': ['ejs:github', 'ejs:npm'], 
                'update_remote_components': True,            
                'js_runtimes': {
                    'deno': {
                        'path': self.deno_path
                    }
                },
                'postprocessor_args': [
                '-map_metadata', '-1',
                ],
            }
            # Download Video
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                v_info = ydl.extract_info(self.url, download=True)
                v_path = v_info.get('filepath')

            # Download Audio
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                a_info = ydl.extract_info(self.url, download=True)
                a_path = a_info.get('filepath')

            return v_path, a_path
        except Exception as e:
            logging.error(f"Gagal download: {e}")
            return None, None

    def remux_video_audio(self, video_path: str, audio_path: str) -> Optional[str]:
        """Menggabungkan video dan audio ke master.mkv (Stream Copy)."""
        output_path = os.path.join(self.raw_dir, 'master.mkv')
        
        if os.path.exists(output_path):
            logging.info(f"file remuxed telah ada: {output_path}")
            return output_path
        else:
            logging.info(f"Memulai remuxing ke: {output_path}")

        def run_remux(gpu_mode):
            v_codec = 'h264_nvenc' if gpu_mode else 'libx264'
            preset = 'p4' if gpu_mode else 'ultrafast'
            
            cmd = [
                self.ffmpeg_path, '-y',
                '-loglevel', 'error',
                '-stats',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', v_codec,
                '-preset', preset,
                '-crf', '18',           # Kualitas visual hampir lossless
                '-r', '30',             # Mengunci frame rate ke 30fps
                '-c:a', 'aac',
                '-ar', '44100',
                '-af', 'aresample=async=1:min_comp=0.001:max_soft_comp=0.01',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-fflags', '+genpts',
                '-avoid_negative_ts', 'make_zero',
                output_path
            ]
            subprocess.run(cmd, check=True)

        try:
            run_remux(self.use_gpu)
            return self.fix_metadata(output_path)
        except subprocess.CalledProcessError as e:
            if self.use_gpu:
                logging.warning(f"⚠️ Remux GPU gagal. Fallback ke CPU... ({e})")
                try:
                    run_remux(False)
                    return self.fix_metadata(output_path)
                except subprocess.CalledProcessError:
                    pass
            logging.error(f"Gagal remux total.")
            return None

    def fix_metadata(self, input_path: str) -> Optional[str]:
        """Memperbaiki timestamp agar sinkron saat dipotong."""
        temp_output = input_path.replace(".mkv", "_fixed.mkv")
        cmd = [self.ffmpeg_path, '-y',
            '-loglevel', 'error',
            '-stats',
            '-i', input_path, 
            '-c', 'copy', 
            temp_output]
        try:
            subprocess.run(cmd, check=True)
            os.replace(temp_output, input_path)
            return input_path
        except:
            return input_path

    def create_raw_clips(self, transcript_json_path: str) -> List[str]:
        """
        Memotong master.mkv menjadi klip-klip kecil berdasarkan JSON.
        Hasilnya adalah klip mentah (Visual + Audio) sebelum diproses AI.
        """
        import os, json, subprocess, logging

        if not os.path.exists(transcript_json_path):
            logging.error(f"File JSON tidak ditemukan: {transcript_json_path}")
            return []

        with open(transcript_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        clips_metadata = data.get('clips', [])
        master_path = os.path.join(self.raw_dir, 'master.mkv')
        
        if not os.path.exists(master_path):
            logging.error("File master.mkv tidak ditemukan. Lakukan remux terlebih dahulu.")
            return []

        # Folder hasil potongan
        clips_dir = os.path.join(self.raw_dir, 'raw_clip_landscape')
        os.makedirs(clips_dir, exist_ok=True)

        created_files = []

        for i, clip in enumerate(clips_metadata):
            start_sec = (clip['start_time'])
            end_sec = (clip['end_time'])
                
            duration = (end_sec - start_sec)
                
            if duration <= 0:
                continue

            output_clip = os.path.join(clips_dir, f"clip_{i+1}.mkv")

            if os.path.exists(output_clip):
                logging.info(f"⏩ Klip sudah ada: {os.path.basename(output_clip)}")
                created_files.append(output_clip)
                continue

            logging.info(f"\n🎬 Memproses Klip {i+1}/{len(clips_metadata)}...")

            def run_clip(gpu_mode):
                v_codec = 'h264_nvenc' if gpu_mode else 'libx264'
                preset = 'p4' if gpu_mode else 'ultrafast'

                cmd = [
                    self.ffmpeg_path, '-y',
                    '-loglevel', 'error',
                    '-stats',
                    '-ss', str(max(0, start_sec - 1)), 
                    '-i', master_path,
                    '-ss', '1' if start_sec >= 1 else str(start_sec),
                    '-t', str(duration),
                    '-c:v', v_codec,
                    '-preset', preset,
                    '-crf', '20',
                    '-c:a', 'aac',
                    '-async', '1',
                    '-af', f'afade=t=in:st=0:d=0.1,afade=t=out:st={duration-0.2}:d=0.2',
                    '-map_metadata', '-1',
                    '-avoid_negative_ts', 'make_zero',          
                    output_clip
                ]
                subprocess.run(cmd, check=True)

            try:
                run_clip(self.use_gpu)
                created_files.append(output_clip)
                logging.info(f"Berhasil membuat klip: {os.path.basename(output_clip)}")
            except subprocess.CalledProcessError:
                if self.use_gpu:
                    logging.warning(f"⚠️ Gagal potong klip {i+1} dengan GPU. Mencoba CPU...")
                    try:
                        run_clip(False)
                        created_files.append(output_clip)
                        continue
                    except subprocess.CalledProcessError:
                        pass
                logging.error(f"Gagal memotong klip {i+1}.")

        return created_files