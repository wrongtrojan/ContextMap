import os
import sys
import json
import yaml
import logging
from pathlib import Path
from minio import Minio
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset, AssetType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [MilvusIngest] - %(levelname)s - %(message)s')
logger = logging.getLogger("MilvusIngest")

class MilvusIngestor:
    def __init__(self, global_cfg_path="configs/model_config.yaml", milvus_cfg_path="configs/milvus_config.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent.parent
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
            self.minio_client.make_bucket(self.bucket_name)

    def _setup_milvus(self):
        """根据 milvus_config.yaml 重新对齐 Schema"""
        conn = self.db_cfg['connection']
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
                FieldSchema(name=sch_cfg['vec'], dtype=DataType.FLOAT_VECTOR, dim=col_cfg['dim']) # 这里使用了 "vector"
            ]
            schema = CollectionSchema(fields, "Academic Multimodal Asset Collection")
            self.collection = Collection(col_cfg['name'], schema)
            
            index_params = {
                "metric_type": col_cfg['metric_type'],
                "index_type": col_cfg['index_type'],
                "params": {"nlist": col_cfg['nlist']}
            }
            self.collection.create_index(field_name=sch_cfg['vec'], index_params=index_params)
        else:
            self.collection = Collection(col_cfg['name'])
        
        self.collection.load()

    def _upload_to_minio(self, local_path: Path, object_name: str):
        try:
            self.minio_client.fput_object(self.bucket_name, object_name, str(local_path))
            return f"minio://{self.bucket_name}/{object_name}"
        except Exception as e:
            logger.error(f"MinIO Upload Error: {e}")
            return str(local_path)

    def ingest_asset(self, asset: AcademicAsset):
        """插入逻辑细节 (完全保留 PDF/Video 的差异化处理)"""
        processed_root = Path(self.model_cfg['paths']['processed_storage'])
        subfolder = "magic-pdf" if asset.asset_type == AssetType.PDF else "video"
        asset_dir = processed_root / subfolder / asset.asset_id
        
        clip_json = asset_dir / "clip_features.json"
        if not clip_json.exists():
            raise FileNotFoundError(f"CLIP features not found for {asset.asset_id}")

        with open(clip_json, 'r', encoding='utf-8') as f:
            features = json.load(f)

        # 容器字段完全对应原始脚本
        names, modalities, types, refs, timestamps, coords, vecs = [], [], [], [], [], [], []

        for item in features:
            # 细节保留：PDF 使用 "type" == "visual", 视频使用 "img_vector" 键存在
            if "img_vector" in item or item.get("type") == "visual":
                vec = item.get("img_vector") or item.get("vector")
                if vec:
                    # 细节保留：视频去 frames 找，PDF 相对 middle.json 找
                    img_name = item.get("frame_name") or item.get("content")
                    if asset.asset_type == AssetType.VIDEO:
                        img_path = asset_dir / "frames" / img_name
                    else:
                        # 针对 PDF 寻找包含 auto 目录的实际路径 (保留原有逻辑)
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

            # 细节保留：文本处理
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
            # 插入顺序严格对应 FieldSchema 的定义
            self.collection.insert([names, modalities, types, refs, timestamps, coords, vecs])
            self.collection.flush()
            return len(names)
        return 0

def run_milvus_ingest(asset: AcademicAsset):
    """新的统一入口"""
    try:
        ingestor = MilvusIngestor()
        count = ingestor.ingest_asset(asset)
        return {"status": "success", "asset_id": asset.asset_id, "vector_inserted": count}
    except Exception as e:
        logger.error(f"Ingestion failed for {asset.asset_id}: {str(e)}")
        return {"status": "error", "message": str(e)}