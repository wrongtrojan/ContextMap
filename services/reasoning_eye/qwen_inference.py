import os
import sys
import yaml
import json
from pathlib import Path
from vllm import LLM, SamplingParams
from qwen_vl_utils import process_vision_info

def load_config():
    """修正版：精准定位 configs/model_config.yaml"""
    current_dir = Path(__file__).resolve().parent
    # 你的脚本在 services/reasoning_eye/，根目录是 current_dir.parent.parent
    # 配置文件在 根目录/configs/model_config.yaml
    config_path = current_dir.parent.parent / "configs" / "model_config.yaml"
        
    if not config_path.exists():
        raise FileNotFoundError(f"致命错误：在以下路径未找到配置文件: {config_path}")
        
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class VisualExpert:
    def __init__(self, config):
        # 你的 model_config.yaml 里定义的路径是 model_paths -> qwen2_vl
        self.model_path = config['model_paths']['qwen2_vl']
        
        print(f"[VisualExpert] 正在加载模型: {self.model_path}")
        
        self.llm = LLM(
            model=self.model_path,
            trust_remote_code=True,
            max_model_len=8192,
            limit_mm_per_prompt={"image": 4, "video": 1},
            gpu_memory_utilization=0.85,
            dtype="bfloat16"
        )
        self.sampling_params = SamplingParams(
            temperature=0.1, 
            max_tokens=1024,
            top_p=0.9
        )

    def reason(self, prompt, visual_content):
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        
        for item in visual_content:
            if not os.path.exists(item):
                print(f"[Warning] 文件不存在: {item}", file=sys.stderr)
                continue
            ext = os.path.splitext(item)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                messages[0]["content"].append({"type": "image", "image": item})
            elif ext in ['.mp4', '.mkv', '.avi', '.mov']:
                messages[0]["content"].append({"type": "video", "video": item})

        prompt_text = self.llm.get_tokenizer().apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        image_inputs, video_inputs = process_vision_info(messages)
        mm_data = {}
        if image_inputs is not None: mm_data["image"] = image_inputs
        if video_inputs is not None: mm_data["video"] = video_inputs
        
        outputs = self.llm.generate(
            [{"prompt": prompt_text, "multi_modal_data": mm_data}], 
            sampling_params=self.sampling_params
        )
        return outputs[0].outputs[0].text

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Qwen2-VL 逻辑执行器")
    # 对标 Wrapper 发出的命令行参数
    parser.add_argument("--image", type=str, help="单张图片路径")
    parser.add_argument("--prompt", type=str, default="请描述图片")
    # 兼容未来可能的批量文件传入
    parser.add_argument("--files", type=str, help="JSON 格式的文件列表")
    
    args = parser.parse_args()
    
    try:
        config = load_config()
        expert = VisualExpert(config)
        
        # 处理输入：如果提供了 --image，构造为列表；如果有 --files，则解析 JSON
        visual_content = []
        if args.image:
            visual_content.append(args.image)
        if args.files:
            visual_content.extend(json.loads(args.files))
            
        if not visual_content:
            raise ValueError("未提供任何图片或视频资源")

        # 执行推理
        result = expert.reason(args.prompt, visual_content)
        
        # 【关键】使用特殊标记包裹 JSON，确保 Wrapper 能精准提取
        print("\n--- RESULT_START ---")
        print(json.dumps({"status": "success", "response": result}, ensure_ascii=False))
        print("--- RESULT_END ---")
        
    except Exception as e:
        # 错误信息打入 stderr，会被 Wrapper 捕获进日志
        sys.stderr.write(f"逻辑层崩溃: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()