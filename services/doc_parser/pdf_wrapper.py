import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_pdf_expert(params):
    # 1. 动态获取包装器所在的绝对路径
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 自动定位项目根目录下的 logs 文件夹
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "doc_parser_log.txt"
    shell_script = os.path.join(SCRIPT_DIR, "mineru_worker.sh")

    # 校验 .sh 文件是否存在
    if not os.path.exists(shell_script):
        return {
            "status": "error", 
            "message": f"未在 {SCRIPT_DIR} 找到 mineru_worker.sh"
        }

    try:
        # 2. 执行 Shell 脚本，并重定向日志
        with open(log_file_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n{'='*20} Task Started: {datetime.now()} {'='*20}\n")
            log_file.flush()
            
            # 使用 Popen 实现静默执行并将输出导向文件
            process = subprocess.Popen(
                ["bash", shell_script],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT)
            )
            
            # 阻塞等待脚本执行完成
            process.wait()

        # 3. 判定结果
        if process.returncode == 0:
            return {
                "status": "success",
                "log_file": str(log_file_path),
                "message": "DocParser 任务执行完毕"
            }
        else:
            return {
                "status": "error",
                "message": f"Shell 脚本执行失败，退出码: {process.returncode}",
                "log_file": str(log_file_path)
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    input_str = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        params = json.loads(input_str)
        response = run_pdf_expert(params)
        # 最终只在终端打印这一行 JSON，不干扰 ToolsManager
        print(json.dumps(response))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))