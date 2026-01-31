import os
import json
import re
import yaml

class AssetCoordinator:
    def __init__(self, force_update=False):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, "../configs/model_config.yaml")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.processed_root = os.path.join(self.config['paths']['processed_storage'], "magic-pdf")
        self.force_update = force_update

    def coordinate_all(self):
        """全量循环处理，包含增量检查逻辑"""
        if not os.path.exists(self.processed_root):
            print(f"未发现目录: {self.processed_root}")
            return

        doc_folders = [f for f in os.listdir(self.processed_root) 
                       if os.path.isdir(os.path.join(self.processed_root, f))]
        
        print(f"检测到 {len(doc_folders)} 个文档文件夹，开始执行精准对齐...")

        for doc_name in doc_folders:
            doc_path = os.path.join(self.processed_root, doc_name)
            # 最终生成的对齐清单文件
            output_file = os.path.join(doc_path, "final_ingestion_manifest.json")

            # --- 增量检查逻辑 ---
            # 如果 manifest 已经存在，且用户没有要求强制更新 (force_update=True)，则跳过
            if os.path.exists(output_file) and not self.force_update:
                print(f"跳过已存在清单的文档 (增量模式): {doc_name}")
                continue

            # 定义依赖文件的路径
            md_path = os.path.join(doc_path, "ocr", f"{doc_name}.md")
            feat_path = os.path.join(doc_path, "chart_features.json")
            content_list_path = os.path.join(doc_path, "ocr", f"{doc_name}_content_list.json")

            if os.path.exists(md_path) and os.path.exists(feat_path):
                print(f"正在处理新文档: {doc_name}")
                self._align_assets(doc_name, md_path, feat_path, content_list_path, output_file)
            else:
                if not os.path.exists(md_path): print(f"  [缺失] Markdown: {md_path}")
                if not os.path.exists(feat_path): print(f"  [缺失] 特征文件: {feat_path}")

    def _align_assets(self, doc_name, md_path, feat_path, content_list_path, output_file):
        """核心对齐逻辑：将文本、图片向量、页码融合"""
        # 1. 加载文件
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(feat_path, 'r', encoding='utf-8') as f:
            features = json.load(f)

        # 2. 从内容列表 JSON 提取页码映射 (建立 页-实体 关联)
        page_map = {}
        if os.path.exists(content_list_path):
            with open(content_list_path, 'r', encoding='utf-8') as f:
                content_list = json.load(f)
                for block in content_list:
                    if "img_path" in block:
                        img_name = os.path.basename(block["img_path"])
                        # page_idx 0-based -> 1-based 自然页码
                        page_map[img_name] = block.get("page_idx", 0) + 1
        else:
            print(f"  [警告] 找不到布局文件，页码将默认为 0: {content_list_path}")

        # 3. 匹配 Markdown 中的图片位置并提取语境 (建立 段落-实体 关联)
        img_pattern = r'!\[.*?\]\((images/.*?)\)'
        matches = list(re.finditer(img_pattern, content))
        
        aligned_results = []
        for match in matches:
            img_rel_path = match.group(1)
            img_filename = os.path.basename(img_rel_path)

            if img_filename in features:
                # 语义打桩：向上取 500 字符作为段落语境
                start_pos = max(0, match.start() - 500)
                context = content[start_pos:match.start()].strip()
                
                aligned_results.append({
                    "doc_name": doc_name,
                    "page_num": page_map.get(img_filename, 0), # 三层索引的关键：页码
                    "image_name": img_filename,
                    "vector": features[img_filename],         # DINOv2 向量
                    "text_context": context,                 # 段落内容
                    "md_anchor": match.group(0)               # MD 锚点
                })

        # 4. 保存清单
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(aligned_results, f, ensure_ascii=False, indent=4)
        print(f"  [成功] 已生成三层索引清单: {doc_name} (包含 {len(aligned_results)} 个实体)")

if __name__ == "__main__":
    # 第一次运行建议设为 False，利用增量逻辑
    # 如果修改了提取算法，可以改为 True 重新生成所有清单
    coordinator = AssetCoordinator(force_update=False)
    coordinator.coordinate_all()