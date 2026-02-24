import os
import sys
import json
import yaml
import time
import logging
from pathlib import Path
from faster_whisper import WhisperModel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [AudioExpert] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("WhisperTranscriber")

class WhisperTranscriber:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.current_file = Path(__file__).resolve()
        self.project_root = self.current_file.parent.parent.parent
        
        config_path = self.project_root / global_cfg_path
        if not config_path.exists():
            logger.error(f"Configuration file missing: {config_path}")
            sys.exit(1)

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info("Configuration loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to parse configuration: {e}")
            sys.exit(1)

        self.model_path = Path(self.config['model_paths']['whisper'])
        self.processed_video_root = Path(self.config['paths']['processed_storage']) / "video"
        
        logger.info(f"Loading Whisper model: {self.model_path.name}")
        self.device = "cuda" if "cuda" in os.environ.get("CUDA_VISIBLE_DEVICES", "cuda") else "cpu"
        
        try:
            self.model = WhisperModel(
                str(self.model_path), 
                device=self.device, 
                compute_type="float16", 
                local_files_only=True
            )
        except Exception as e:
            logger.error(f"Model initialization failed, please check weight format: {e}")
            sys.exit(1)

    def process_all(self, force_reprocess=False):
        if not self.processed_video_root.exists():
            logger.error(f"Directory missing: {self.processed_video_root}")
            return

        video_folders = [d for d in self.processed_video_root.iterdir() if d.is_dir()]
        total_tasks = len(video_folders)
        
        logger.info(f"========= Starting Audio Transcription Pipeline (Total {total_tasks} pending tasks) =========")

        for idx, folder in enumerate(video_folders):
            logger.info(f"\n[{idx+1}/{total_tasks}] Task object: {folder.name}")
            
            output_json = folder / "transcript.json"
            if output_json.exists() and not force_reprocess:
                logger.info(f"==== [SKIP] Incremental skip: transcript.json already exists ====")
                continue

            target_mp4 = next(folder.glob("*.standard.mp4"), None)
            if not target_mp4:
                logger.warning(f"==== [WARN] Skip: .standard.mp4 not found (Please run VideoSlicer first) ====")
                continue

            try:
                self._transcribe_video(target_mp4, output_json)
            except Exception as e:
                logger.error(f"Task failed: {folder.name} -> {e}")

        logger.info("\n========= All audio transcription tasks have ended =========")

    def _transcribe_video(self, mp4_path, output_json):
        logger.info(f"--- [START] Extracting semantic text: {mp4_path.name} ---")
        start_t = time.time()

        prompt = "这是一段学术讲解视频。请使用简体中文转录，确保术语准确。"

        segments, info = self.model.transcribe(
            str(mp4_path), 
            beam_size=5, 
            vad_filter=True,
            initial_prompt=prompt,
            language="zh"
        )

        logger.info(f"Detected language: {info.language} | Video duration: {info.duration:.2f}s")

        results = []
        for segment in segments:
            results.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            })
            if len(results) % 20 == 0:
                logger.info(f"Transcription progress: {segment.end:.1f} seconds of semantic extraction completed...")

        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump({
                "source": mp4_path.name,
                "language": info.language,
                "duration": info.duration,
                "segments": results
            }, f, ensure_ascii=False, indent=4)

        elapsed = time.time() - start_t
        logger.info(f"Transcription complete: Generated {len(results)} semantic segments | Time elapsed: {elapsed:.2f}s")

if __name__ == "__main__":
    transcriber = WhisperTranscriber()
    transcriber.process_all(force_reprocess=False)