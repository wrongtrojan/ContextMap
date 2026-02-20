import logging
from fastapi import APIRouter, Depends, HTTPException
from core.assets_manager import GlobalAssetManager, AssetStatus

logger = logging.getLogger("AssetsAPI")
router = APIRouter()
manager = GlobalAssetManager()

@router.post("/sync")
async def trigger_sync():
    """
    [API] 申请处理资产：唤醒后台 Worker 消费队列
    """
    res = await manager.start_queue_processing()
    return res

@router.get("/structure")
async def get_structure(asset_id: str):
    """
    [API] 获取结构化大纲
    """
    asset = manager.get_asset_status(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset["status"] != AssetStatus.READY.value:
        return {"status": "processing", "current_step": asset["status"]}

    # 逻辑：返回处理后的路径信息，前端根据此路径请求静态资源或由后端读取返回
    return {
        "status": "success",
        "asset_id": asset_id,
        "processed_path": asset["processed_path"],
        "message": "Asset is ready for structural view"
    }

@router.get("/preview")
async def get_preview(asset_id: str):
    """
    [API] 申请预览资产的原始或处理后路径
    """
    asset = manager.get_asset_status(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    return {
        "asset_id": asset_id,
        "raw_path": asset["raw_path"],
        "processed_path": asset["processed_path"],
        "type": asset["type"]
    }