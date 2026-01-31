import os
import json
import torch
import yaml
import numpy as np
from PIL import Image
import torchvision.transforms as T

class DINOv2Worker:
    def __init__(self, force_reprocess=False):
        # 1. 配置加载
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "../../configs/model_config.yaml")
        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_config = yaml.safe_load(f)
        
        self.model_root = self.full_config['model_paths']['dinov2']
        self.weight_path = os.path.join(self.model_root, "dinov2_vitl14_pretrain.pth")
        self.processed_root = os.path.join(self.full_config['paths']['processed_storage'], "magic-pdf")
        
        self.force_reprocess = force_reprocess # 是否强制重新提取
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 2. 模型加载 (仅在确实有任务需要处理时才会打印加载信息)
        self._model = None
        self._transform = None

    @property
    def model(self):
        if self._model is None:
            print(f"--- 开启离线模式，加载 DINOv2 权重 ---")
            
            # 指向你本地缓存的代码目录
            # 刚才你第一次运行成功时，代码已经下载到了这里
            hub_dir = "/home/liangqing/.cache/torch/hub/facebookresearch_dinov2_main"
            
            # 使用 source='local' 强制从本地读取模型定义，不联网
            self._model = torch.hub.load(hub_dir, 'dinov2_vitl14', source='local', pretrained=False)
            
            # 加载权重
            self._model.load_state_dict(torch.load(self.weight_path, map_location='cpu', weights_only=True))
            self._model.to(self.device).eval()
        return self._model

    @property
    def transform(self):
        if self._transform is None:
            self._transform = T.Compose([
                T.Resize(256, interpolation=T.InterpolationMode.BICUBIC),
                T.CenterCrop(224),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
        return self._transform

    def batch_process(self):
        if not os.path.exists(self.processed_root):
            print(f"错误: 找不到目录 {self.processed_root}")
            return

        for doc_name in os.listdir(self.processed_root):
            doc_path = os.path.join(self.processed_root, doc_name)
            if not os.path.isdir(doc_path): continue

            output_json = os.path.join(doc_path, "chart_features.json")
            
            # --- 增量检测逻辑 ---
            if os.path.exists(output_json) and not self.force_reprocess:
                print(f"跳过已处理文档: {doc_name}")
                continue

            img_dir = os.path.join(doc_path, "ocr", "images")
            if os.path.exists(img_dir):
                # 检查目录下是否有图片
                images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                if not images:
                    print(f"文档 {doc_name} 的 images 目录为空，生成空特征文件。")
                    with open(output_json, "w") as f: json.dump({}, f)
                    continue

                print(f"正在提取特征: {doc_name} ({len(images)} 张图片)...")
                features = self._extract_features(img_dir, images)
                
                with open(output_json, "w", encoding='utf-8') as f:
                    json.dump(features, f, indent=4)
                print(f"保存成功: {output_json}")

    def _extract_features(self, img_dir, image_list):
        results = {}
        for img_name in image_list:
            img_path = os.path.join(img_dir, img_name)
            try:
                image = Image.open(img_path).convert("RGB")
                img_tensor = self.transform(image).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    embedding = self.model(img_tensor).cpu().numpy().flatten()
                results[img_name] = embedding.tolist()
            except Exception as e:
                print(f"处理 {img_name} 失败: {e}")
        return results

if __name__ == "__main__":
    # 默认不强制重跑
    worker = DINOv2Worker(force_reprocess=False)
    worker.batch_process()