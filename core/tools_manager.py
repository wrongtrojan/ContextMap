import subprocess
import json
import os
import yaml
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Brain-Center] - %(levelname)s - %(message)s')
logger = logging.getLogger("ToolsManager")

class ToolsManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent
        full_config_path = self.project_root / config_path
        
        with open(full_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.base_dir = str(self.project_root)
        logger.info("✅ Academic Brain Toolbox is online: All expert environments have been mounted.")

    def _dispatch_raw(self, env_key, script_rel_path, params=None):
        python_exe = self.envs.get(env_key)
        if not python_exe or not os.path.exists(python_exe):
            return {"status": "error", "message": f"Environment {env_key} configuration is invalid or does not exist"}

        script_path = os.path.join(self.base_dir, script_rel_path)
        json_params = json.dumps(params if params else {}, ensure_ascii=False)

        try:
            result = subprocess.run(
                [python_exe, script_path, json_params],
                capture_output=True,
                text=True,
                cwd=self.base_dir
            )
            
            if result.returncode != 0:
                logger.error(f"❌ Expert {script_rel_path} exited abnormally: {result.stderr}")
                return {"status": "error", "message": "Subprocess execution failed", "details": result.stderr}

            output_lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if not output_lines:
                return {"status": "error", "message": "Expert did not return a valid JSON result"}
                
            return json.loads(output_lines[-1])

        except Exception as e:
            return {"status": "error", "message": f"Brain dispatch link failure: {str(e)}"}

    # ================= Explicit Expert Interfaces ==================

    def call_visual_eye(self, image_path, prompt):
        logger.info(f"👁️ [Visual Reasoning] Processing image: {os.path.basename(image_path)}")
        return self._dispatch_raw(
            "visual_reasoning_env", 
            "services/reasoning_eye/visual_wrapper.py", 
            {"image": image_path, "prompt": prompt}
        )

    def call_whisper_node(self, audio_id=None):
        logger.info("👂 [Audio Transcription] Starting audio transcription expert pipeline...")
        return self._dispatch_raw(
            "audio_processing_env", 
            "data_layer/audio_pro/audio_wrapper.py", 
            {"audio_id": audio_id}
        )

    def call_pdf_expert(self, pdf_id=None):
        logger.info(f"📄 [Doc Parsing] Scheduling MinerU parsing task: {pdf_id}: {pdf_id}")
        return self._dispatch_raw(
            "pdf_processing_env", 
            "data_layer/pdf_pro/pdf_wrapper.py", 
            {"pdf_id": pdf_id}
        )

    def call_sandbox(self, expression, mode="eval"):
        logger.info(f"🔢 [Scientific Computing] Executing expression: {expression}")
        return self._dispatch_raw(
            "scientific_env", 
            "services/sandbox/sandbox_wrapper.py", 
            {"expression": expression, "mode": mode}
        )

    def call_video_slicer(self, video_path=None):
        logger.info("✂️ [Video Slicing] Starting full video asset preprocessing...")
        return self._dispatch_raw(
            "video_vision_env", 
            "data_layer/video_pro/video_wrapper.py", 
            {"video_path": video_path}
        )


if __name__ == "__main__":
    manager = ToolsManager()
    