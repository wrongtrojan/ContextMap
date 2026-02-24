import asyncio
import json
import os
import yaml
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from core.assets_manager import AcademicAsset

# --- 基础日志函数 ---
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE_PATH = LOG_DIR / "services.log"

def log_message(level: str, msg: str):
    """
    基础日志重定向：同时打印到控制台并追加到 services.log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    formatted_msg = f"{timestamp} - [ServicesManager] - {level} - {msg}"
    
    # 输出到控制台
    print(formatted_msg)
    
    # 追加到文件
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"CRITICAL: Failed to write log to file: {e}")

class ServicesManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        """
        初始化多环境网关
        """
        self.project_root = Path(__file__).resolve().parent.parent
        full_config_path = self.project_root / config_path
        
        if not full_config_path.exists():
            log_message("ERROR", f"Config file not found: {full_config_path}")
            raise FileNotFoundError(f"Config file not found: {full_config_path}")

        with open(full_config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.wrapper_dir = self.project_root / "services" / "wrappers"
        log_message("INFO", "ServicesManager initialized successfully.")

    async def _dispatch_async(self, env_key: str, script_name: str, asset: Optional[AcademicAsset] = None, params: Optional[Dict] = None, timeout: int = 3600) -> Dict[str, Any]:
        """
        核心异步分派逻辑：启动子进程，等待并解析返回的 JSON 结果
        """
        python_exe = self.envs.get(env_key)
        script_path = self.wrapper_dir / script_name

        if not python_exe or not os.path.exists(python_exe):
            err_msg = f"Python interpreter not found for env: {env_key}"
            log_message("ERROR", err_msg)
            return {"status": "error", "message": err_msg}
        
        if not script_path.exists():
            err_msg = f"Wrapper script not found: {script_name}"
            log_message("ERROR", err_msg)
            return {"status": "error", "message": err_msg}

        # 准备子进程环境变量
        current_env = os.environ.copy()
        venv_bin = str(Path(python_exe).parent)
        current_env["PATH"] = f"{venv_bin}{os.pathsep}{current_env.get('PATH', '')}"
        current_env["PYTHONUNBUFFERED"] = "1"
        
        # 准备输入参数
        input_data = {}
        asset_id_str = "N/A"
        if asset:
            input_data = asset.to_dict()
            asset_id_str = asset.asset_id
        if params:
            input_data.update(params)
        
        input_str = json.dumps(input_data)

        log_message("INFO", f"Dispatching: [{env_key}] -> {script_name} (Asset: {asset_id_str})")

        try:
            # 启动异步子进程
            process = await asyncio.create_subprocess_exec(
                python_exe, "-u", str(script_path), input_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
                env=current_env
            )

            try:
                # 等待任务完成
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                log_message("ERROR", f"Task timeout ({timeout}s) for {script_name}")
                return {"status": "error", "message": f"Task timed out after {timeout}s", "asset_id": asset_id_str}

            # 解码输出
            out_str = stdout.decode().strip()
            err_str = stderr.decode().strip()

            if process.returncode != 0:
                log_message("ERROR", f"Task failed [Exit {process.returncode}] in {script_name}: {err_str}")
                return {
                    "status": "error", 
                    "exit_code": process.returncode, 
                    "message": err_str,
                    "asset_id": asset_id_str
                }

            # 解析最后一行 JSON
            try:
                last_line = out_str.splitlines()[-1] if out_str else "{}"
                result = json.loads(last_line)
                log_message("INFO", f"Task success: {script_name}")
                return result
            except (json.JSONDecodeError, IndexError):
                log_message("WARNING", f"Task {script_name} finished but output was not JSON. Raw: {out_str[:100]}...")
                return {
                    "status": "partial_success", 
                    "raw_output": out_str, 
                    "message": "Task finished but output was not valid JSON"
                }

        except Exception as e:
            log_message("ERROR", f"Unexpected error during dispatch: {str(e)}")
            log_message("DEBUG", traceback.format_exc()) # 记录详细堆栈
            return {"status": "error", "message": str(e)}

    # --- 异步服务接口 (保持不变) ---

    async def start_pdf_recognition(self, asset: AcademicAsset):
        return await self._dispatch_async("doc_recognize", "pdf_recognize.py", asset=asset)

    async def start_video_recognition(self, asset: AcademicAsset):
        return await self._dispatch_async("video_recognize", "video_recognize.py", asset=asset)

    async def start_clip_indexing(self, asset: AcademicAsset):
        return await self._dispatch_async("data_stream", "clip_work.py", asset=asset)

    async def start_milvus_ingestion(self, asset: AcademicAsset):
        return await self._dispatch_async("data_stream", "milvus_ingest.py", asset=asset)

    async def start_structure_generation(self, asset: AcademicAsset):
        return await self._dispatch_async("agent_logic", "structure_generate.py", asset=asset)

    async def call_visual_expert(self, image_path: str, prompt: str):
        params = {"image": image_path, "prompt": prompt}
        return await self._dispatch_async("visual_inference", "visual_inference.py", params=params)
    
    async def call_sandbox_expert(self, image_path: str, prompt: str):
        params = {"image": image_path, "prompt": prompt}
        return await self._dispatch_async("sandbox_inference", "sandbox_inference.py", params=params)