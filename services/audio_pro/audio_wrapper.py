import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_whisper(params):
    # 1. 路径定位与日志初始化
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 回溯到项目根目录下的 logs 文件夹
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "audio_pro_log.txt"
    logic_script = os.path.join(SCRIPT_DIR, "whisper_node.py")
    python_exe = sys.executable

    try:
        # 2. 以追加模式 (Append) 打开日志文件
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Whisper Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()

            # 3. 使用 Popen 实时流式写入日志，终端保持静默
            process = subprocess.Popen(
                [python_exe, "-u", logic_script], # -u 确保日志实时从 stdout 刷新到文件
                stdout=log_file,
                stderr=subprocess.STDOUT, # 将错误信息也合并到同一个日志文件中
                text=True,
                cwd=str(PROJECT_ROOT)
            )

            # 阻塞等待转录专家执行完成
            process.wait()

        # 4. 根据退出码返回结构化状态给大脑
        if process.returncode == 0:
            return {
                "status": "success",
                "worker": "Whisper-Node",
                "log_file": str(log_file_path),
                "message": "音频转录流水线执行完毕"
            }
        else:
            return {
                "status": "error",
                "message": f"Whisper 专家执行异常，退出码: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # 解析大脑传来的参数
    try:
        input_data = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
        response = run_whisper(input_data)
        # 核心：终端只打印这一行 JSON，供 ToolsManager 捕获
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))