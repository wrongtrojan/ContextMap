import os
import sys
import json
import yaml
import httpx
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# 注入项目根目录以加载 core 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType
from core.prompts_manager import PromptManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [StructureGen] - %(levelname)s - %(message)s')
logger = logging.getLogger("StructureGenerator")

class StructureGenerator:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        # 加载配置
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        # 初始化 Prompt 管理器
        self.prompt_manager = PromptManager(str(self.project_root / "core/prompts"))
        
        # API 配置 (优先从环境变量或配置读取)
        self.api_url = self.config.get("llm", {}).get("api_url", "https://api.deepseek.com/v1/chat/completions")
        self.api_key = self.config.get("llm", {}).get("api_key", "YOUR_API_KEY")

    def _extract_context(self, asset: AcademicAsset) -> str:
        """
        从已处理的中间文件中提取文本内容作为 LLM 上下文
        """
        processed_root = Path(self.config['paths']['processed_storage'])
        
        if asset.asset_type == AssetType.PDF:
            # 读取 MinerU 生成的内容列表
            # 路径逻辑同之前重构：magic-pdf/{id}/.../middle.json
            base_path = processed_root / "magic-pdf" / asset.asset_id
            middle_files = list(base_path.glob("**/auto/middle.json"))
            if not middle_files:
                raise FileNotFoundError(f"Missing processed PDF content for {asset.asset_id}")
            
            with open(middle_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 提取前 5000 字左右的文本作为摘要参考
                full_text = []
                for page in data.get("pdf_intermediate_dict", []):
                    for block in page.get("middle_blocks", []):
                        if block.get("type") in ["text", "title"]:
                            full_text.append(block.get("text", ""))
                return "\n".join(full_text)[:10000] # 截断防止 Token 溢出

        elif asset.asset_type == AssetType.VIDEO:
            # 读取 Whisper 生成的转录文本
            transcript_path = processed_root / "video" / asset.asset_id / "transcript.json"
            if not transcript_path.exists():
                raise FileNotFoundError(f"Missing transcript for video {asset.asset_id}")
            
            with open(transcript_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                segments = data.get("segments", [])
                return "\n".join([f"[{s['start']}s]: {s['text']}" for s in segments])[:10000]

        return ""

    async def generate_outline(self, asset: AcademicAsset):
        """核心逻辑：渲染 Prompt 并调用 DeepSeek"""
        context = self._extract_context(asset)
        
        # 渲染 core/prompts/structural_outline.txt (或 .yaml)
        prompt = self.prompt_manager.render(
            "structural_outline", 
            raw_context=context, 
            asset_type=asset.asset_type.value
        )

        logger.info(f"发送请求至 DeepSeek 处理资产: {asset.asset_id}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
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
                
                # 确定保存路径
                output_subfolder = "magic-pdf" if asset.asset_type == AssetType.PDF else "video"
                save_dir = Path(self.config['paths']['processed_storage']) / output_subfolder / asset.asset_id
                save_dir.mkdir(parents=True, exist_ok=True)
                
                save_path = save_dir / "summary_outline.json"
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "asset_id": asset.asset_id,
                        "generated_at": datetime.now().isoformat(),
                        "outline": outline_content
                    }, f, ensure_ascii=False, indent=4)
                
                return {
                    "status": "success",
                    "save_path": str(save_path),
                    "asset_id": asset.asset_id
                }

            except Exception as e:
                logger.error(f"DeepSeek 调用失败: {str(e)}")
                return {"status": "error", "message": str(e)}

async def run_structure_generate(asset: AcademicAsset):
    """供外部调用的异步包装函数"""
    generator = StructureGenerator()
    return await generator.generate_outline(asset)

if __name__ == "__main__":
    # 命令行直接运行逻辑
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            # 简易实例化转换
            asset_obj = AcademicAsset(
                asset_id=asset_data['asset_id'],
                asset_type=AssetType(asset_data['asset_type']),
                raw_path=asset_data.get('asset_raw_path', "")
            )
            result = asyncio.run(run_structure_generate(asset_obj))
            print(json.dumps(result))
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))