import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_slicer(params):
    # 1. 路径定位
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 定位根目录及日志文件
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "video_vision_log.txt"
    logic_script = os.path.join(SCRIPT_DIR, "video_slicer.py")
    python_exe = sys.executable

    try:
        # 2. 以追加模式打开日志
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} VideoSlicer Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()

            # 3. 启动进程，实时将 stdout/stderr 导向日志文件
            # 使用 -u 确保 Python 日志流实时写入，不被缓冲区阻塞
            process = subprocess.Popen(
                [python_exe, "-u", logic_script],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT)
            )

            # 阻塞直到切片任务结束
            process.wait()

        # 4. 根据退出码返回状态
        if process.returncode == 0:
            return {
                "status": "success",
                "worker": "VideoSlicer-Node",
                "log_file": str(log_file_path),
                "message": "视频切片流水线执行完毕"
            }
        else:
            return {
                "status": "error",
                "message": f"视频切片执行失败，退出码: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # 解析来自大脑的 JSON 指令（目前你的 slicer 是全量扫描，params 可为空）
    try:
        input_data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        response = run_slicer(input_data)
        # 保持终端整洁，只输出这一行最终 JSON
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))