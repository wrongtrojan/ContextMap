import os
import json
import logging
import asyncio
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# --- 配置与日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [AssetSystem] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AssetManager")

class AssetStatus(Enum):
    UPLOADING = "Uploading"     # 接口已调用，文件正在写入磁盘
    RAW = "Raw"                 # 文件写入完成，进入待处理队列
    RECOGNIZING= "recognizing"  # 处理过程中（如视频识别或PDF解析）
    CLIPING = "Cliping"
    STRUCTURING = "Structuring"
    INGESTING ="Ingesting"
    READY = "Ready"             # 处理完成
    FAILED = "Failed"           # 发生错误

class AssetType(Enum):
    PDF = "pdf"
    VIDEO = "video"

class AcademicAsset:
    def __init__(self, asset_id: str, asset_type: AssetType, raw_path: str):
        self.asset_id = asset_id
        self.asset_type = asset_type
        self.status = AssetStatus.UPLOADING # 初始状态设为上传中
        self.asset_raw_path = raw_path
        self.asset_processed_path = ""
        self.created_at = datetime.now().isoformat()
        self.retry_count = 0

    def to_dict(self):
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type.value,
            "status": self.status.value,
            "asset_raw_path": self.asset_raw_path,
            "asset_processed_path": self.asset_processed_path,
            "created_at": self.created_at,
            "retry_count": self.retry_count
        }

    @classmethod
    def from_dict(cls, data: dict):
        asset = cls(data["asset_id"], AssetType(data["asset_type"]), data["asset_raw_path"])
        asset.status = AssetStatus(data["status"])
        asset.asset_processed_path = data.get("asset_processed_path", "")
        asset.created_at = data.get("created_at")
        asset.retry_count = data.get("retry_count", 0)
        return asset

class GlobalAssetManager:
    _instance = None
    _lock = asyncio.Lock() # 协程锁，保证并发安全

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GlobalAssetManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, storage_root: str = "./storage"):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.db_file = self.storage_root / "assets_registry.json"
        
        self.assets_map: Dict[str, AcademicAsset] = {} 
        self.pending_queue: List[str] = [] # 只有状态为 RAW 的才进入此队列
        
        self._initialized = True
        self.load_state()

    # --- 核心业务逻辑接口 ---

    async def register_new_upload(self, asset_id: str, asset_type: AssetType, expected_path: str):
        """
        [逻辑接口 1]: 当 API 被调用时，首先实例化资产。
        此时状态为 UPLOADING，不会被后台 Worker 抓取。
        """
        async with self._lock:
            if asset_id in self.assets_map:
                logger.warning(f"Asset {asset_id} already exists. Skipping registration.")
                return
            
            new_asset = AcademicAsset(asset_id, asset_type, expected_path)
            self.assets_map[asset_id] = new_asset
            self.save_state()
            logger.info(f"==> [REGISTERED] Asset {asset_id} created. Status: UPLOADING")

    async def update_to_raw(self, asset_id: str):
        """
        [逻辑接口 2]: 当文件真实上传成功并落盘后调用。
        将状态改为 RAW，并正式加入待处理队列。
        """
        async with self._lock:
            asset = self.assets_map.get(asset_id)
            if asset and asset.status == AssetStatus.UPLOADING:
                asset.status = AssetStatus.RAW
                if asset_id not in self.pending_queue:
                    self.pending_queue.append(asset_id)
                self.save_state()
                logger.info(f"==> [RAW READY] Asset {asset_id} upload complete. Added to queue.")

    async def get_next_task(self) -> Optional[AcademicAsset]:
        """供后台处理进程调用的接口"""
        async with self._lock:
            if not self.pending_queue:
                return None
            aid = self.pending_queue.pop(0)
            asset = self.assets_map[aid]
            asset.status = AssetStatus.RECOGNIZING
            return asset

    # --- 持久化 ---

    def save_state(self):
        data = {
            "assets_map": {aid: a.to_dict() for aid, a in self.assets_map.items()},
            "updated_at": datetime.now().isoformat()
        }
        with open(self.db_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def load_state(self):
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for aid, a_data in data.get("assets_map", {}).items():
                        asset = AcademicAsset.from_dict(a_data)
                        self.assets_map[aid] = asset
                        # 恢复时：只有 RAW 状态的任务需要重新入队
                        if asset.status == AssetStatus.RAW:
                            self.pending_queue.append(aid)
                logger.info(f"State loaded. {len(self.assets_map)} assets in registry.")
            except Exception as e:
                logger.error(f"Persistence error: {e}")