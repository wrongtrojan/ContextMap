import os
import json
import yaml
import logging
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# 1. 日志配置
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MilvusIngestor")

class MilvusIngestor:
    def __init__(self, force_reset=False):
        # --- 路径修正逻辑 ---
        # self.script_dir 是 ~/AcademicAgent-Suite/data_layer
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        # self.root_dir 是 ~/AcademicAgent-Suite
        self.root_dir = os.path.dirname(self.script_dir)
        # 配置文件在 ~/AcademicAgent-Suite/configs
        config_dir = os.path.join(self.root_dir, "configs")
        
        logger.info(f"正在从以下目录加载配置: {config_dir}")
        
        # 加载双配置
        try:
            with open(os.path.join(config_dir, "model_config.yaml"), 'r', encoding='utf-8') as f:
                self.model_cfg = yaml.safe_load(f)
            with open(os.path.join(config_dir, "milvus_config.yaml"), 'r', encoding='utf-8') as f:
                self.db_cfg = yaml.safe_load(f)
        except FileNotFoundError as e:
            logger.error(f"配置文件缺失，请检查路径: {e}")
            raise

        # 2. 连接 Milvus
        conn = self.db_cfg['connection']
        connections.connect("default", host=conn['host'], port=conn['port'])
        self.col_name = self.db_cfg['collection']['name']
        
        # 强制重置逻辑
        if force_reset and utility.has_collection(self.col_name):
            utility.drop_collection(self.col_name)
            logger.warning(f"⚠️ 已重置集合: {self.col_name}")

        self._setup_collection()

    def _setup_collection(self):
        """定义 Schema"""
        if utility.has_collection(self.col_name):
            self.collection = Collection(self.col_name)
            self.collection.load()
            return

        s = self.db_cfg['schema']
        c = self.db_cfg['collection']

        fields = [
            FieldSchema(name=s['pk'], dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="doc_name", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=50), 
            FieldSchema(name="content_ref", dtype=DataType.VARCHAR, max_length=1000),
            FieldSchema(name=s['vec'], dtype=DataType.FLOAT_VECTOR, dim=c['dim'])
        ]
        
        schema = CollectionSchema(fields, "Academic Multimodal Index")
        self.collection = Collection(self.col_name, schema)

        index_params = {
            "metric_type": c['metric_type'],
            "index_type": c['index_type'],
            "params": {"nlist": c['nlist']}
        }
        self.collection.create_index(field_name=s['vec'], index_params=index_params)
        self.collection.load()
        logger.info(f"✅ Milvus 集合 {self.col_name} 初始化成功")

    def _is_doc_ingested(self, doc_name):
        res = self.collection.query(expr=f'doc_name == "{doc_name}"', output_fields=["id"], limit=1)
        return len(res) > 0

    def run_ingestion(self):
        """同步 multimodal_features.json 到 Milvus"""
        # 这里的 processed_storage 已经在 model_config.yaml 里定义为绝对路径了
        processed_root = os.path.join(self.model_cfg['paths']['processed_storage'], "magic-pdf")
        
        if not os.path.exists(processed_root):
            logger.error(f"未找到 magic-pdf 处理目录: {processed_root}")
            return

        total_count = 0
        for doc_name in os.listdir(processed_root):
            doc_dir = os.path.join(processed_root, doc_name)
            feature_path = os.path.join(doc_dir, "multimodal_features.json")
            
            if not os.path.exists(feature_path): continue
            if self._is_doc_ingested(doc_name):
                logger.info(f"⏭️ 跳过已入库文档: {doc_name}")
                continue

            logger.info(f"🚀 正在同步: {doc_name}")
            with open(feature_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            names, types, refs, vecs = [], [], [], []

            # 提取图片
            for img_name, img_data in data.get("images", {}).items():
                names.append(doc_name)
                types.append("image")
                refs.append(img_name)
                vecs.append(img_data if isinstance(img_data, list) else img_data.get("embedding"))

            # 提取文本
            for chunk in data.get("text_chunks", []):
                names.append(doc_name)
                types.append("text")
                refs.append(chunk.get("text_slice", "text_chunk"))
                vecs.append(chunk["embedding"])

            if names:
                self.collection.insert([names, types, refs, vecs])
                total_count += len(names)
                logger.info(f"📈 插入数据: {len(names)} 条")

        self.collection.flush()
        logger.info(f"✨ 同步结束，总计入库 {total_count} 条向量。")

if __name__ == "__main__":
    # 第一次运行建议为 True
    ingestor = MilvusIngestor(force_reset=False)
    ingestor.run_ingestion()