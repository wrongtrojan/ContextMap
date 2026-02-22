import os
import sys
import json
import yaml
import httpx
import asyncio
import logging
import dotenv
from pathlib import Path
from datetime import datetime

# 加载环境变量
dotenv.load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.assets_manager import AcademicAsset, AssetType
from core.prompts_manager import PromptManager

# --- 日志配置重定向 ---
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file_path = LOG_DIR / "structure_generate.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [StructureGen] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler(sys.stdout) # 同时输出到控制台方便调试
    ]
)
logger = logging.getLogger("StructureGenerator")

class StructureGenerator:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = PROJECT_ROOT
        
        # Load configuration
        config_path = self.project_root / global_cfg_path
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # Initialize Prompt Manager
        self.prompt_manager = PromptManager()
        
        # API Configuration
        llm_cfg = self.config.get("llm", {})
        self.api_url = llm_cfg.get("api_url", "https://api.deepseek.com/v1/chat/completions")
        self.api_key = os.getenv("DEEPSEEK_API_KEY")

    def _extract_context(self, asset: AcademicAsset) -> str:
        """Extract text content from processed files as LLM context"""
        processed_root = Path(self.config['paths']['processed_storage'])
        
        try:
            if asset.asset_type == AssetType.PDF:
                # Logic for MinerU: magic-pdf/{id}/.../middle.json
                clean_id=asset.asset_id.replace(".pdf", "")  # Sanitize ID for filesystem
                base_path = processed_root / "magic-pdf" / clean_id
                middle_files = base_path/"ocr"/f"{clean_id}_middle.json"
                if not middle_files.exists():
                    raise FileNotFoundError(f"Missing processed PDF content (middle.json) for {asset.asset_id}")
                
                with open(middle_files, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                content_to_send = data.get("pdf_info", data)
                return json.dumps(content_to_send, ensure_ascii=False)[:15000] 

            elif asset.asset_type == AssetType.VIDEO:
                # Logic for Whisper: video/{id}/transcript.json
                transcript_path = processed_root / "video" / asset.asset_id / "transcript.json"
                if not transcript_path.exists():
                    raise FileNotFoundError(f"Missing transcript for video {asset.asset_id}")
                
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    segments = data.get("segments", [])
                    return "\n".join([f"[{s['start']}s]: {s['text']}" for s in segments])[:10000]
        except Exception as e:
            logger.error(f"Context extraction failed for {asset.asset_id}: {str(e)}")
            raise

        return ""

    async def generate_outline(self, asset: AcademicAsset):
        """Render prompt and call DeepSeek API"""
        logger.info(f"Starting structure generation for asset: {asset.asset_id}")
        
        try:
            context = self._extract_context(asset)
            
            # Render prompt
            prompt = self.prompt_manager.render(
                "structural_outline", 
                raw_context=context, 
                asset_type=asset.asset_type.value
            )

            logger.info(f"Sending request to DeepSeek for asset: {asset.asset_id}")
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "You are a professional academic assistant. Return results in JSON format."},
                            {"role": "user", "content": prompt}
                        ],
                        "response_format": {"type": "json_object"}
                    }
                )
                response.raise_for_status()
                res_data = response.json()
                outline_content = json.loads(res_data['choices'][0]['message']['content'])
                
                # Determine save path
                processed_root = Path(self.config['paths']['processed_storage'])
                if asset.asset_type == AssetType.PDF:
                    clean_id = asset.asset_id.replace(".pdf", "")
                    save_dir = processed_root / "magic-pdf" / clean_id
                else:
                    save_dir = processed_root / "video" / asset.asset_id
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / "summary_outline.json"
                
                result_payload = {
                    "asset_id": asset.asset_id,
                    "generated_at": datetime.now().isoformat(),
                    "outline": outline_content
                }
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(result_payload, f, ensure_ascii=False, indent=4)
                
                logger.info(f"Successfully generated outline for {asset.asset_id}. Saved to: {save_path}")
                return {
                    "status": "success",
                    "save_path": str(save_path),
                    "asset_id": asset.asset_id
                }

        except Exception as e:
            logger.error(f"DeepSeek call or processing failed for {asset.asset_id}: {str(e)}")
            return {"status": "error", "message": str(e), "asset_id": asset.asset_id}

async def run_structure_generate(asset: AcademicAsset):
    """Async wrapper for external calls"""
    generator = StructureGenerator()
    return await generator.generate_outline(asset)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            # 移除复杂的判断逻辑，强制执行标准接口
            asset_obj = AcademicAsset.from_dict(asset_data)
            
            result = asyncio.run(run_structure_generate(asset_obj))
            print(json.dumps(result))
        except Exception as e:
            error_res = {"status": "error", "message": f"CLI execution error: {str(e)}"}
            print(json.dumps(error_res))