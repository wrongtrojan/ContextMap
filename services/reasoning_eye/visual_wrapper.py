import sys
import json
import subprocess
import os
from datetime import datetime
from pathlib import Path

def run_visual_inference(params):
    # 1. 路径定位
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = Path(SCRIPT_DIR).resolve().parent.parent
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    
    log_file_path = LOG_DIR / "resoning_eye_log.txt"
    # 注意：确保这里指向你真正的推理逻辑文件
    logic_script = os.path.join(SCRIPT_DIR, "qwen_inference.py")
    python_exe = sys.executable

    try:
        with open(log_file_path, "a", encoding="utf-8") as log_f:
            # 这里的 logic_script 指向你刚才改好的 qwen_inference.py
            process = subprocess.Popen(
                [sys.executable, "-u", str(logic_script), 
                 "--image", params.get("image", ""), 
                 "--prompt", params.get("prompt", "")],
                stdout=subprocess.PIPE, # 这里改回 PIPE，我们要在大脑端实时过滤
                stderr=log_f,           # 错误信息去日志
                text=True,
                cwd=str(PROJECT_ROOT)
            )
            
            final_json_raw = ""
            capture_mode = False
            
            # 实时读取 stdout，过滤噪音，只留结果
            for line in process.stdout:
                log_f.write(line) # 所有的 INFO 依然存入日志
                if "--- RESULT_START ---" in line:
                    capture_mode = True
                    continue
                if "--- RESULT_END ---" in line:
                    capture_mode = False
                    continue
                if capture_mode:
                    final_json_raw += line
            
            process.wait()

        if process.returncode == 0 and final_json_raw:
            return json.loads(final_json_raw.strip())
        else:
            return {"status": "error", "message": "逻辑层未返回有效结果"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    try:
        # 接收 JSON 指令
        input_json = sys.argv[1] if len(sys.argv) > 1 else "{}"
        params = json.loads(input_json)
        
        response = run_visual_inference(params)
        
        # 【全场唯一输出】确保大脑拿到的只有这一行 JSON
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Wrapper入口崩溃: {str(e)}"}))