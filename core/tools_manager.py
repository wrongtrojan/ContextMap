import subprocess
import json
import os
import yaml
import logging

# 初始化日志，方便我们观察调用过程
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ToolsManager:
    def __init__(self, config_path="configs/model_config.yaml"):
        # 1. 确保配置文件存在
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件未找到: {config_path}")
            
        # 2. 加载全局路径配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.envs = self.config.get('environments', {})
        self.base_dir = self.config.get('paths', {}).get('base_dir', "")
        
        logging.info("ToolsManager 初始化成功，配置已加载。")

    def dispatch(self, env_key, script_rel_path, params=None):
        """
        跨环境分派任务的核心方法
        """
        # 获取该专家的 Python 解释器路径
        python_exe = self.envs.get(env_key)
        
        if not python_exe:
            return {"status": "error", "message": f"环境配置 {env_key} 不存在"}
        
        if not os.path.exists(python_exe):
            return {"status": "error", "message": f"解释器路径无效: {python_exe}"}

        # 拼接脚本的绝对路径
        script_path = os.path.join(self.base_dir, script_rel_path)
        if not os.path.exists(script_path):
            return {"status": "error", "message": f"脚本文件不存在: {script_path}"}
        
        # 将参数转换为 JSON 字符串以便跨进程传递
        json_params = json.dumps(params if params else {})

        try:
            # 调用对应的 Conda 环境执行脚本
            result = subprocess.run(
                [python_exe, script_path, json_params],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            return {"status": "error", "message": "子进程执行报错", "stderr": e.stderr}
        except Exception as e:
            return {"status": "error", "message": str(e)}