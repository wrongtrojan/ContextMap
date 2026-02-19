import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 引入资产定义
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from core.assets_manager import AcademicAsset

def run_video_recognize(asset: AcademicAsset):
    """
    重构后的编排器：
    1. 采用严格的行过滤逻辑提取 Worker 结果
    2. 支持带日志输出的 stdout 解析
    """
    WRAPPERS_DIR = Path(__file__).parent.absolute()
    ORIGINAL_DIR = WRAPPERS_DIR.parent / "original"
    PROJECT_ROOT = WRAPPERS_DIR.parent.parent
    
    python_exe = sys.executable

    try:
        # --- Stage 1: OpenCV 处理 ---
        cv_script = ORIGINAL_DIR / "opencv_worker.py"
        cv_cmd = [
            python_exe, str(cv_script),
            "--asset_id", asset.asset_id,
            "--asset_raw_path", asset.asset_raw_path
        ]
        
        # 使用 check_output 捕获输出
        cv_res = subprocess.check_output(cv_cmd, text=True, stderr=subprocess.STDOUT)
        
        # 【关键解析修改】：只找以 SUCCESS 开头的行
        cv_success_line = next((line for line in cv_res.strip().split('\n') if line.startswith("SUCCESS")), None)
        if not cv_success_line:
            raise Exception(f"OpenCVWorker finished but no SUCCESS signal found. Output: {cv_res[:200]}")
        
        # 解析格式: SUCCESS|FRAME_COUNT:50|STANDARD_PATH:/path/xxx
        cv_parts = cv_success_line.split('|')
        frame_count = cv_parts[1].split(':')[1]
        standard_path = cv_parts[2].split(':')[1]

        # --- Stage 2: Whisper 处理 ---
        ws_script = ORIGINAL_DIR / "whisper_worker.py"
        ws_cmd = [
            python_exe, str(ws_script),
            "--asset_id", asset.asset_id,
            "--asset_processed_path", str(Path(standard_path).parent)
        ]
        
        ws_res = subprocess.check_output(ws_cmd, text=True, stderr=subprocess.STDOUT)
        
        # 【关键解析修改】：同理，提取 Whisper 的成功行
        ws_success_line = next((line for line in ws_res.strip().split('\n') if line.startswith("SUCCESS")), None)
        if not ws_success_line:
            raise Exception(f"WhisperWorker finished but no SUCCESS signal found.")
            
        # 解析格式: SUCCESS|TRANSCRIPT_PATH:/path/xxx
        transcript_path = ws_success_line.split('|')[1].split(':')[1]

        # --- 最终聚合结果 ---
        return {
            "status": "success",
            "asset_id": asset.asset_id,
            "frame_count": int(frame_count),
            "transcript_path": transcript_path,
            "processed_path": str(Path(standard_path).parent),
            "timestamp": datetime.now().isoformat()
        }

    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "asset_id": asset.asset_id,
            "message": f"Worker process crashed: {e.output}"
        }
    except Exception as e:
        return {
            "status": "error", 
            "asset_id": asset.asset_id, 
            "message": f"Orchestrator error: {str(e)}"
        }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asset_obj = AcademicAsset.from_dict(json.loads(sys.argv[1]))
        print(json.dumps(run_video_recognize(asset_obj)))