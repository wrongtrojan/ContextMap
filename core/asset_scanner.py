import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# Standard logging configuration using English as per development standards
logger = logging.getLogger("AssetScanner")

class AssetScanner:
    def __init__(self, base_processed_path: str = "storage/processed"):
        """
        Initialize scanner with support for multi-engine output structures (magic-pdf, etc.)
        """
        self.root_path = Path(base_processed_path)
        # Map logical type to physical directory name
        self.type_mapping = {
            "video": "video",
            "pdf": "magic-pdf"  # Aligned with your actual storage structure
        }

    def scan_all_assets(self) -> List[Dict[str, Any]]:
        """
        Builds a global asset map by traversing engine-specific output directories.
        """
        global_map = []
        
        if not self.root_path.exists():
            logger.warning(f"Scan target path missing: {self.root_path}")
            return global_map

        for asset_type, dir_name in self.type_mapping.items():
            type_dir = self.root_path / dir_name
            if not type_dir.exists():
                continue

            for asset_folder in type_dir.iterdir():
                if asset_folder.is_dir():
                    try:
                        asset_info = self._extract_asset_metadata(asset_folder, asset_type)
                        global_map.append(asset_info)
                    except Exception as e:
                        logger.error(f"Error scanning folder {asset_folder.name}: {str(e)}")
        
        logger.info(f"Asset scan complete. Found {len(global_map)} synchronized assets.")
        return global_map

    def _locate_raw_file_url(self, folder: Path, asset_type: str) -> str:
        """
        Heuristic to find the viewable source file for the frontend.
        For magic-pdf: looks inside folder/ocr/*_origin.pdf
        For video: looks for source mp4 in storage/raw_files
        """
        asset_id = folder.name
        
        if asset_type == "pdf":
            # MinerU/Magic-PDF specific structure: folder/ocr/xxx_origin.pdf
            ocr_dir = folder / "ocr"
            if ocr_dir.exists():
                # Find the first pdf that ends with _origin.pdf
                origin_pdfs = list(ocr_dir.glob("*_origin.pdf"))
                if origin_pdfs:
                    rel_path = origin_pdfs[0].relative_to(self.root_path.parent.parent)
                    return f"/{rel_path}"
            
            # Fallback to raw_files if processed origin not found
            return f"/raw/PDF/{asset_id}.pdf"
        
        else:
            # Video fallback
            return f"/raw/video/{asset_id}.mp4"

    def _extract_asset_metadata(self, folder: Path, asset_type: str) -> Dict[str, Any]:
        """
        Deep extraction of asset info including processed status and direct access URLs.
        """
        asset_id = folder.name
        outline_file = folder / "summary_outline.json"
        
        # 1. Resolve URLs for frontend components
        # raw_url: for the PDF viewer or Video player
        # preview_url: for the sidebar thumbnail
        raw_url = self._locate_raw_file_url(folder, asset_type)
        
        # 2. Build basic metadata structure
        metadata = {
            "asset_id": asset_id,
            "type": asset_type,
            "display_name": asset_id.replace("_", " ").title(),
            "status": "ready",
            "raw_url": raw_url,
            "preview_url": f"/processed/{self.type_mapping[asset_type]}/{asset_id}/preview.jpg",
            "outline": [],
            "stats": {
                "last_modified": os.path.getmtime(folder),
                "local_path": str(folder)
            }
        }

        # 3. Enrich with cognitive outline if available
        if outline_file.exists():
            try:
                with open(outline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    metadata["outline"] = data.get("outline", [])
                    metadata["display_name"] = data.get("title", metadata["display_name"])
            except Exception as e:
                logger.error(f"Failed to read summary for {asset_id}: {str(e)}")
                metadata["status"] = "error"
        else:
            # Check if the folder is still being populated by tools
            metadata["status"] = "processing"

        return metadata