import os
import json
import yaml
import torch
import logging
import numpy as np
from PIL import Image
import transformers
from transformers import CLIPProcessor, CLIPModel

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CLIPWorker")
transformers.utils.logging.set_verbosity_error()

class CLIPWorker:
    def __init__(self, force_reprocess=False):
        # 1. 加载配置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "../../configs/model_config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.full_config = yaml.safe_load(f)
        
        self.model_path = self.full_config['model_paths']['clip']
        self.processed_root = os.path.join(self.full_config['paths']['processed_storage'], "magic-pdf")
        self.force_reprocess = force_reprocess
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self._model = None
        self._processor = None

    @property
    def model(self):
        if self._model is None:
            logger.info(f"--- 开启离线模式，加载 CLIP 权重: {self.model_path} ---")
            self._model = CLIPModel.from_pretrained(self.model_path).to(self.device)
            self._model.eval()
        return self._model

    @property
    def processor(self):
        if self._processor is None:
            self._processor = CLIPProcessor.from_pretrained(self.model_path)
        return self._processor

    def _get_aligned_embedding(self, outputs):
        """
        更加强健的解包逻辑：无论 outputs 是对象、字典还是张量，都强制提取出第一个 Tensor
        """
        tensor = None
        
        # 1. 尝试直接获取已知的嵌入属性
        if hasattr(outputs, "image_embeds"):
            tensor = outputs.image_embeds
        elif hasattr(outputs, "text_embeds"):
            tensor = outputs.text_embeds
        elif hasattr(outputs, "pooler_output"):
            tensor = outputs.pooler_output
            
        # 2. 如果还是没拿到，尝试作为字典或列表处理
        if tensor is None:
            if isinstance(outputs, (list, tuple)):
                tensor = outputs[0]
            elif isinstance(outputs, dict):
                tensor = list(outputs.values())[0]
            elif hasattr(outputs, "last_hidden_state"):
                # 如果只有隐藏层，我们取平均值
                tensor = outputs.last_hidden_state.mean(dim=1)
            else:
                # 最后的兜底：假设它本身就是一个可迭代的对象
                try:
                    tensor = outputs[0]
                except:
                    tensor = outputs

        # 3. 现在的 tensor 应该是真正的 PyTorch Tensor 了
        # 我们进行最后的转换
        if hasattr(tensor, "detach"):
            return tensor.detach().cpu().numpy().flatten().tolist()
        else:
            # 如果走到这里还不是 tensor，那只能是 numpy 数组或列表了
            return np.array(tensor).flatten().tolist()

    def batch_process(self):
        if not os.path.exists(self.processed_root):
            logger.error(f"路径不存在: {self.processed_root}")
            return

        for doc_name in os.listdir(self.processed_root):
            doc_path = os.path.join(self.processed_root, doc_name)
            if not os.path.isdir(doc_path): continue

            output_json = os.path.join(doc_path, "multimodal_features.json")
            
            if os.path.exists(output_json) and not self.force_reprocess:
                logger.info(f"跳过已处理文档: {doc_name}")
                continue

            logger.info(f">>> 正在处理文档: {doc_name}")
            ocr_dir = os.path.join(doc_path, "ocr")
            img_dir = os.path.join(ocr_dir, "images")
            content_list_path = os.path.join(ocr_dir, f"{doc_name}_content_list.json")

            doc_results = {"images": {}, "text_chunks": []}

            # 1. 处理图片 (使用投影接口确保维度对齐)
            if os.path.exists(img_dir):
                images = [f for f in os.listdir(img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                for img_name in images:
                    try:
                        image = Image.open(os.path.join(img_dir, img_name)).convert("RGB")
                        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                        with torch.no_grad():
                            # get_image_features 会自动通过投影层映射到对齐空间
                            outputs = self.model.get_image_features(**inputs)
                            doc_results["images"][img_name] = self._get_aligned_embedding(outputs)
                    except Exception as e:
                        logger.warning(f"图片 {img_name} 向量化失败: {e}")

            # 2. 处理文本 (使用投影接口确保维度对齐)
            if os.path.exists(content_list_path):
                try:
                    with open(content_list_path, 'r', encoding='utf-8') as f:
                        content_data = json.load(f)
                    for item in content_data:
                        text = item.get("text") or item.get("text_content") or ""
                        if len(text.strip()) < 5: continue 

                        inputs = self.processor(text=[text], return_tensors="pt", padding=True, truncation=True).to(self.device)
                        with torch.no_grad():
                            # get_text_features 会自动映射到与图片相同的对齐空间
                            outputs = self.model.get_text_features(**inputs)
                            embedding = self._get_aligned_embedding(outputs)
                        
                        doc_results["text_chunks"].append({
                            "type": item.get("type", "text"),
                            "text_slice": text[:50], 
                            "embedding": embedding
                        })
                except Exception as e:
                    logger.warning(f"文本块处理失败: {e}")

            # 3. 保存结果
            with open(output_json, "w", encoding='utf-8') as f:
                json.dump(doc_results, f, indent=4, ensure_ascii=False)
            logger.info(f"文档 {doc_name} 特征保存成功")

if __name__ == "__main__":
    # 强制清理并重跑一次
    worker = CLIPWorker(force_reprocess=True)
    worker.batch_process()