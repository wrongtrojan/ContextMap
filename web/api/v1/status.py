from fastapi import APIRouter
from core.assets_manager import GlobalAssetManager

router = APIRouter()
manager = GlobalAssetManager()

@router.get("/single_asset")
async def get_single_status(asset_id: str):
    """
    [API] 查询单一资产状态
    """
    asset = manager.get_asset_status(asset_id)
    if not asset:
        return {"status": "error", "message": "Asset ID not found"}
    return {"status": "success", "data": asset}

@router.get("/global_assets")
async def get_global_status():
    """
    [API] 查询全局资产统计与队列状态
    """
    # 获取 GlobalAssetManager 中的统计信息
    status_info = manager.get_global_status()
    return {
        "status": "success",
        "data": status_info
    }