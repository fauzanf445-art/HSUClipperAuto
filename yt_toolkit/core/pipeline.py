import os
import logging
import gc
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from yt_toolkit.engine.processor import VideoProcessor
from .utils import get_video_resolution, print_progress

def _process_clip_task(task_data):
    """
    Worker function untuk memproses klip secara paralel (Multiprocessing).
    Ditempatkan di level modul agar bisa di-pickle oleh Windows.
    """
    try:
        clip_num = task_data['clip_num']
        
        # Inisialisasi Processor baru untuk setiap proses
        # Progress callback diset None agar output konsol tidak berantakan
        with VideoProcessor(model_path=task_data['model_path'], use_gpu=task_data['use_gpu']) as proc:
            success = proc.process_video(
                str(task_data['raw_path']), 
                str(task_data['final_path']), 
                progress_callback=None,
                subtitle_path=str(task_data['ass_path']),
                fonts_dir=task_data['fonts_dir']
            )

        # Cleanup file mentah jika sukses
        if success and task_data['cleanup']:
            try:
                if task_data['raw_path'].exists(): os.remove(task_data['raw_path'])
                if os.path.exists(task_data['ass_path']): os.remove(task_data['ass_path'])
            except Exception:
                pass
        
        return clip_num, success, None

    except Exception as e:
        return task_data.get('clip_num'), False, str(e)

class ClipProductionPipeline:
    """
    Menangani orkestrasi produksi klip video secara batch:
    1. Partial Download (Menghemat bandwidth)
    2. Caption Generation (Whisper)
    3. Manajemen VRAM (Release Whisper sebelum load MediaPipe)
    4. Visual Processing (MediaPipe + FFmpeg)
    """
    def __init__(self, downloader, captioner, paths, config):
        self.downloader = downloader
        self.captioner = captioner
        self.paths = paths
        self.config = config

    def run(self, clips, use_gpu_visual):
        """
        Menjalankan pipeline produksi.
        Args:
            clips: List data klip dari JSON.
            use_gpu_visual: Boolean untuk mengaktifkan GPU pada VideoProcessor.
        """
        print("[2/3] Produksi Klip (Batch Processing)...")
        
        if not clips:
            print("❌ Tidak ada klip yang ditemukan dalam rencana.")
            return False

        # Siapkan folder output final
        video_final_dir = self.paths.TEMP_FINAL / self.downloader.asset_folder_name
        video_final_dir.mkdir(parents=True, exist_ok=True)
        
        # --- FASE 1: PREPARE (Download & Caption) ---
        print(f"\n🔄 FASE 1: Persiapan Aset & Captioning ({len(clips)} Klip)")
        
        processing_queue = [] # Antrean untuk fase rendering

        for i, clip_data in enumerate(clips):
            try:
                clip_num = int(clip_data.get('id', i + 1))
                
                # Tentukan path output final di sini untuk pengecekan Resume
                final_clip_path = video_final_dir / f"clip_{clip_num:02d}_final.mkv"
                
                # [RESUME CHECK] Jika file final sudah ada, lewati proses berat ini
                if final_clip_path.exists():
                    print(f"   ⏩ [Klip {clip_num}] Sudah ada. Melewati...")
                    continue

            except (ValueError, TypeError):
                clip_num = i + 1
                
            print(f"\n   📥 [Klip {clip_num}/{len(clips)}] Download & Transkripsi...")

            try:
                # A. PARTIAL DOWNLOAD
                downloaded_files = self.downloader.download_clips_directly([clip_data])
                if not downloaded_files:
                    print(f"      ⚠️ Gagal download klip {clip_num}. Melewati...")
                    continue
                
                raw_clip_path = Path(downloaded_files[0])
                
                # B. GENERATE CAPTION
                orig_w, orig_h = get_video_resolution(str(raw_clip_path))
                
                tgt_h = orig_h
                tgt_w = int(orig_h * 9 / 16)

                print(f"      📝 Generating Subtitle ({tgt_w}x{tgt_h})...")
                ass_path = self.captioner.generate_styled_ass(
                    audio_source_path=str(raw_clip_path),
                    target_w=tgt_w,
                    target_h=tgt_h
                )
                
                processing_queue.append({
                    'raw_path': raw_clip_path,
                    'ass_path': ass_path,
                    'final_path': final_clip_path,
                    'clip_num': clip_num
                })
            except Exception as e:
                logging.error(f"Gagal menyiapkan klip {clip_num}: {e}", exc_info=True)
                print(f"      ❌ Error pada klip {clip_num}: {e}")
                continue

        # --- RELEASE WHISPER ---
        print(f"\n♻️  Melepaskan Model AI (Whisper) untuk menghemat VRAM...")
        if self.captioner:
            self.captioner.release()
        
        # [GARBAGE COLLECTION] Paksa pembersihan memori sebelum masuk fase visual berat
        gc.collect()
        
        # --- FASE 2: VISUAL PROCESSING ---
        print(f"\n🔄 FASE 2: Rendering Visual ({len(processing_queue)} Klip)")
        
        if not processing_queue:
            print("❌ Tidak ada klip yang berhasil disiapkan.")
            return False

        # Tentukan jumlah worker paralel
        # Jika GPU: Batasi 2 worker agar VRAM/Encoder aman.
        # Jika CPU: Gunakan (Total Core - 1) agar sistem tetap responsif.
        if use_gpu_visual:
            max_workers = 2
        else:
            max_workers = max(1, multiprocessing.cpu_count() - 1)

        print(f"🚀 Memulai Parallel Rendering dengan {max_workers} workers...")

        # Siapkan data task
        tasks = []
        for item in processing_queue:
            tasks.append({
                'raw_path': item['raw_path'],
                'final_path': item['final_path'],
                'ass_path': item['ass_path'],
                'clip_num': item['clip_num'],
                'model_path': str(self.paths.DETECTOR_MODEL_PATH),
                'use_gpu': use_gpu_visual,
                'fonts_dir': str(self.paths.FONTS_DIR),
                'cleanup': self.config.get('cleanup_enabled', True)
            })

        # Eksekusi Paralel
        completed_count = 0
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_clip = {executor.submit(_process_clip_task, t): t['clip_num'] for t in tasks}
            
            for future in as_completed(future_to_clip):
                c_num = future_to_clip[future]
                try:
                    _, success, err = future.result()
                    if success:
                        print(f"   ✅ [Klip {c_num}] Selesai.")
                        completed_count += 1
                    else:
                        print(f"   ❌ [Klip {c_num}] Gagal: {err}")
                except Exception as exc:
                    print(f"   ❌ [Klip {c_num}] Exception: {exc}")

        print(f"\n✅ [2/3] Produksi selesai. {completed_count} klip berhasil dibuat.")
        return True
