import os
import sys
import json
import yaml
import torch
import logging
import numpy as np
from PIL import Image
from pathlib import Path
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel

# 屏蔽 tqdm 干扰日志
import tqdm
class DisabledTqdm:
    def __init__(self, *args, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def __iter__(self): return self
    def __next__(self): raise StopIteration
    def __getattr__(self, name): return lambda *args, **kwargs: None
tqdm.tqdm = DisabledTqdm

# 注入项目根目录以加载 core 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [CLIPWork] - %(levelname)s - %(message)s')
logger = logging.getLogger("CLIPWork")

class CLIPWorker:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # 加载模型逻辑 (完全保留)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        model_id = self.config['model_paths']['clip']
        self.model = CLIPModel.from_pretrained(model_id).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_id)
        
        # 视频对齐参数 (完全保留)
        self.window_pre = 2.0
        self.window_post = 3.0

    def _get_vec(self, image_path=None, text=None):
        """核心提取与归一化逻辑 (完全保留)"""
        with torch.no_grad():
            if image_path:
                image = Image.open(image_path).convert("RGB")
                inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                features = self.model.get_image_features(**inputs)
            elif text:
                inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                features = self.model.get_text_features(**inputs)
            else:
                return None
            
            features = F.normalize(features, p=2, dim=-1)
            return features.cpu().numpy().tolist()[0]

    def _process_pdf(self, asset: AcademicAsset):
        """MinerU 解析细节 (完全保留)"""
        base_dir = Path(self.config['paths']['processed_storage']) / "magic-pdf" / asset.asset_id
        
        # 寻找 middle.json 的递归逻辑 (保留)
        middle_json_list = list(base_dir.glob("**/auto/middle.json"))
        if not middle_json_list:
            raise FileNotFoundError(f"MinerU middle.json not found in {base_dir}")
        
        middle_json = middle_json_list[0]
        with open(middle_json, 'r', encoding='utf-8') as f:
            data = json.load(f)

        results = []
        for page in data.get("pdf_intermediate_dict", []):
            page_idx = page.get("page_idx")
            for block in page.get("middle_blocks", []):
                block_type = block.get("type")
                
                if block_type in ["text", "title", "reference"]:
                    text_content = block.get("text", "").strip()
                    if len(text_content) > 10:
                        vec = self._get_vec(text=text_content)
                        # 保持原始输出字典结构
                        results.append({
                            "type": "text", "page": page_idx, "vector": vec, 
                            "content": text_content[:100], "bbox": block.get("bbox")
                        })
                
                elif block_type in ["image", "table"]:
                    img_ref = block.get("image_path")
                    if img_ref:
                        img_path = middle_json.parent / img_ref
                        if img_path.exists():
                            vec = self._get_vec(image_path=img_path)
                            results.append({
                                "type": "visual", "page": page_idx, "vector": vec,
                                "content": str(img_ref), "bbox": block.get("bbox")
                            })

        output_path = base_dir / "clip_features.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return len(results)

    def _process_video(self, asset: AcademicAsset):
        """视频滑动窗口对齐细节 (完全保留)"""
        base_dir = Path(self.config['paths']['processed_storage']) / "video" / asset.asset_id
        frame_dir = base_dir / "frames"
        transcript_path = base_dir / "transcript.json"

        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript missing for {asset.asset_id}")

        with open(transcript_path, 'r', encoding='utf-8') as f:
            segments = json.load(f).get("segments", [])

        frame_files = sorted(list(frame_dir.glob("*.jpg")))
        results = []

        for img_path in frame_files:
            try:
                # 原始文件名时间戳解析 (保留)
                ts = float(img_path.stem.split('_')[1])
            except: continue

            # 原始窗口过滤逻辑 (保留)
            neighbor_texts = [s['text'] for s in segments 
                             if not (s['end'] < ts - self.window_pre or s['start'] > ts + self.window_post)]
            combined_text = " ".join(neighbor_texts).strip()

            img_vec = self._get_vec(image_path=img_path)
            text_vec = self._get_vec(text=combined_text) if combined_text else None

            # 保持原始输出字典结构 (img_vector / text_vector)
            results.append({
                "timestamp": ts,
                "frame_name": img_path.name,
                "img_vector": img_vec,
                "text_vector": text_vec,
                "content": combined_text,
                "need_vlm": True if (len(combined_text) < 15) else False
            })

        output_path = base_dir / "clip_features.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        return len(results)

def run_clip_work(asset: AcademicAsset):
    """新的统一入口"""
    try:
        worker = CLIPWorker()
        if asset.asset_type == AssetType.PDF:
            count = worker._process_pdf(asset)
        elif asset.asset_type == AssetType.VIDEO:
            count = worker._process_video(asset)
        else:
            return {"status": "error", "message": "Unsupported asset type"}
        return {"status": "success", "asset_id": asset.asset_id, "vector_count": count}
    except Exception as e:
        logger.error(f"CLIPWork failed for {asset.asset_id}: {str(e)}")
        return {"status": "error", "message": str(e)}