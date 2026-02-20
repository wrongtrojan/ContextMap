import os
import sys
import json
import yaml
import logging
from pathlib import Path
from datetime import datetime
from minio import Minio
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

# 注入项目根目录以加载 core 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType

# --- 日志重定向逻辑 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file_path = LOG_DIR / "milvus_ingest.log"

# 配置日志：同时输出到控制台和文件，使用 UTF-8 编码防止中文乱码
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MilvusIngest] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MilvusIngest")

class MilvusIngestor:
    def __init__(self, global_cfg_path="configs/model_config.yaml", milvus_cfg_path="configs/milvus_config.yaml"):
        self.project_root = PROJECT_ROOT
        with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
            self.model_cfg = yaml.safe_load(f)
        with open(self.project_root / milvus_cfg_path, 'r', encoding='utf-8') as f:
            self.db_cfg = yaml.safe_load(f)

        # MinIO 初始化 (保留原始连接细节)
        self.minio_client = Minio(
            "localhost:9000",
            access_key="minioadmin",  
            secret_key="minioadmin",
            secure=False
        )
        self.bucket_name = "academic-assets"
        self._setup_minio()
        self._setup_milvus()

    def _setup_minio(self):
        if not self.minio_client.bucket_exists(self.bucket_name):
            logger.info(f"Creating MinIO bucket: {self.bucket_name}")
            self.minio_client.make_bucket(self.bucket_name)

    def _setup_milvus(self):
        """根据 milvus_config.yaml 重新对齐 Schema"""
        conn = self.db_cfg['connection']
        logger.info(f"Connecting to Milvus at {conn['host']}:{conn['port']}...")
        connections.connect("default", host=conn['host'], port=conn['port'])
        
        col_cfg = self.db_cfg['collection']
        sch_cfg = self.db_cfg['schema']

        if not utility.has_collection(col_cfg['name']):
            fields = [
                FieldSchema(name=sch_cfg['pk'], dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name=sch_cfg['asset_name'], dtype=DataType.VARCHAR, max_length=200),
                FieldSchema(name=sch_cfg['modality'], dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name=sch_cfg['content_type'], dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name=sch_cfg['content_ref'], dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name=sch_cfg['timestamp'], dtype=DataType.DOUBLE),
                FieldSchema(name=sch_cfg['coordinates'], dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name=sch_cfg['vec'], dtype=DataType.FLOAT_VECTOR, dim=col_cfg['dim'])
            ]
            schema = CollectionSchema(fields, "Academic Multimodal Asset Collection")
            self.collection = Collection(col_cfg['name'], schema)
            
            index_params = {
                "metric_type": col_cfg['metric_type'],
                "index_type": col_cfg['index_type'],
                "params": {"nlist": col_cfg['nlist']}
            }
            self.collection.create_index(field_name=sch_cfg['vec'], index_params=index_params)
            logger.info(f"Collection {col_cfg['name']} created and indexed.")
        else:
            self.collection = Collection(col_cfg['name'])
        
        self.collection.load()

    def _upload_to_minio(self, local_path: Path, object_name: str):
        try:
            self.minio_client.fput_object(self.bucket_name, object_name, str(local_path))
            return f"minio://{self.bucket_name}/{object_name}"
        except Exception as e:
            logger.error(f"MinIO Upload Error for {local_path}: {e}")
            return str(local_path)

    def ingest_asset(self, asset: AcademicAsset):
        """插入逻辑细节 (完全保留 PDF/Video 的差异化处理)"""
        processed_root = Path(self.model_cfg['paths']['processed_storage'])
        subfolder = "magic-pdf" if asset.asset_type == AssetType.PDF else "video"
        asset_dir = processed_root / subfolder / asset.asset_id
        
        clip_json = asset_dir / "clip_features.json"
        if not clip_json.exists():
            raise FileNotFoundError(f"CLIP features not found for {asset.asset_id}")

        logger.info(f"Starting ingestion for asset: {asset.asset_id}")
        with open(clip_json, 'r', encoding='utf-8') as f:
            features = json.load(f)

        names, modalities, types, refs, timestamps, coords, vecs = [], [], [], [], [], [], []

        for item in features:
            # 处理视觉特征
            if "img_vector" in item or item.get("type") == "visual":
                vec = item.get("img_vector") or item.get("vector")
                if vec:
                    img_name = item.get("frame_name") or item.get("content")
                    if asset.asset_type == AssetType.VIDEO:
                        img_path = asset_dir / "frames" / img_name
                    else:
                        middle_json_list = list(asset_dir.glob("**/auto/middle.json"))
                        img_path = middle_json_list[0].parent / img_name if middle_json_list else asset_dir / img_name
                    
                    remote_ref = self._upload_to_minio(img_path, f"{asset.asset_id}/{Path(img_name).name}") if img_path.exists() else img_name
                    
                    names.append(asset.asset_id)
                    modalities.append(asset.asset_type.value)
                    types.append("visual")
                    refs.append(remote_ref)
                    timestamps.append(item.get("timestamp", item.get("page", 0.0)))
                    coords.append(json.dumps(item.get("bbox", [])))
                    vecs.append(vec)

            # 处理文本特征
            if "text_vector" in item or item.get("type") == "text":
                vec = item.get("text_vector") or item.get("vector")
                if vec:
                    names.append(asset.asset_id)
                    modalities.append(asset.asset_type.value)
                    types.append("text")
                    refs.append(item.get("content") or "")
                    timestamps.append(item.get("timestamp", item.get("page", 0.0)))
                    coords.append(json.dumps(item.get("bbox", [])))
                    vecs.append(vec)

        if names:
            self.collection.insert([names, modalities, types, refs, timestamps, coords, vecs])
            self.collection.flush()
            logger.info(f"Successfully inserted {len(names)} vectors for {asset.asset_id}")
            return len(names)
        return 0

def run_milvus_ingest(asset: AcademicAsset):
    """新的统一入口"""
    logger.info(f"\n{'='*20} Milvus Ingest Start: {datetime.now()} {'='*20}")
    try:
        ingestor = MilvusIngestor()
        count = ingestor.ingest_asset(asset)
        return {"status": "success", "asset_id": asset.asset_id, "vector_inserted": count}
    except Exception as e:
        logger.error(f"Ingestion critical error for {asset.asset_id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            asset_data = json.loads(sys.argv[1])
            # 强制规范化：将字典转换为对象
            asset_obj = AcademicAsset.from_dict(asset_data)
            print(json.dumps(run_milvus_ingest(asset_obj)))
        except Exception as e:
            logger.error(f"Entry point error: {e}")
            print(json.dumps({"status": "error", "message": str(e)}))