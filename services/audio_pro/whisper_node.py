import os
import sys
import json
import yaml
import time
import logging
from pathlib import Path
from faster_whisper import WhisperModel

# ================= 日志配置 (对齐 Slicer 风格) =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [AudioExpert] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("WhisperTranscriber")

class WhisperTranscriber:
    def __init__(self, global_cfg_path="configs/model_config.yaml"):
        # 1. 自动定位项目根目录并加载配置
        self.current_file = Path(__file__).resolve()
        self.project_root = self.current_file.parent.parent.parent
        
        config_path = self.project_root / global_cfg_path
        if not config_path.exists():
            logger.error(f"配置文件缺失: {config_path}")
            sys.exit(1)

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info("配置加载成功。")
        except Exception as e:
            logger.error(f"解析配置失败: {e}")
            sys.exit(1)

        # 2. 从配置读取路径
        self.model_path = Path(self.config['model_paths']['whisper'])
        self.processed_video_root = Path(self.config['paths']['processed_storage']) / "video"
        
        # 3. 初始化模型 (自动检测 CUDA)
        logger.info(f"正在加载 Whisper 模型: {self.model_path.name}")
        self.device = "cuda" if "cuda" in os.environ.get("CUDA_VISIBLE_DEVICES", "cuda") else "cpu"
        
        try:
            self.model = WhisperModel(
                str(self.model_path), 
                device=self.device, 
                compute_type="float16", # 针对讲解视频优化性能
                local_files_only=True
            )
        except Exception as e:
            logger.error(f"模型初始化失败，请检查权重格式: {e}")
            sys.exit(1)

    def process_all(self, force_reprocess=False):
        """循环处理视频目录，支持增量与任务提示"""
        if not self.processed_video_root.exists():
            logger.error(f"目录缺失: {self.processed_video_root}")
            return

        # 获取待处理的文件夹列表
        video_folders = [d for d in self.processed_video_root.iterdir() if d.is_dir()]
        total_tasks = len(video_folders)
        
        logger.info(f"========= 启动音频转录流水线 (共 {total_tasks} 个待检任务) =========")

        for idx, folder in enumerate(video_folders):
            logger.info(f"\n[{idx+1}/{total_tasks}] 任务对象: {folder.name}")
            
            # 增量检查
            output_json = folder / "transcript.json"
            if output_json.exists() and not force_reprocess:
                logger.info(f"==== [SKIP] 增量跳过: 已存在 transcript.json ====")
                continue

            # 寻找标准视频文件
            target_mp4 = next(folder.glob("*.standard.mp4"), None)
            if not target_mp4:
                logger.warning(f"==== [WARN] 跳过: 未找到 .standard.mp4 (请先运行 VideoSlicer) ====")
                continue

            try:
                self._transcribe_video(target_mp4, output_json)
            except Exception as e:
                logger.error(f"处理异常: {folder.name} -> {e}")

        logger.info("\n========= 所有音频转录任务已结束 =========")

    def _transcribe_video(self, mp4_path, output_json):
        """针对讲解视频优化的转录逻辑"""
        logger.info(f"--- [开始处理] 正在提取语义文本: {mp4_path.name} ---")
        start_t = time.time()

        # initial_prompt 强制纠正讲解视频常见的繁简混乱
        prompt = "这是一段学术讲解视频。请使用简体中文转录，确保术语准确。"

        # vad_filter=True 过滤长静音，提升讲解类视频的断句质量
        segments, info = self.model.transcribe(
            str(mp4_path), 
            beam_size=5, 
            vad_filter=True,
            initial_prompt=prompt,
            language="zh"
        )

        logger.info(f"检测语言: {info.language} | 视频时长: {info.duration:.2f}s")

        results = []
        for segment in segments:
            results.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            })
            # 模拟 Slicer 的进度反馈
            if len(results) % 20 == 0:
                logger.info(f"转录进度: 已完成 {segment.end:.1f} 秒语义提取...")

        # 存储结果
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump({
                "source": mp4_path.name,
                "language": info.language,
                "duration": info.duration,
                "segments": results
            }, f, ensure_ascii=False, indent=4)

        elapsed = time.time() - start_t
        logger.info(f"转录完成: 生成 {len(results)} 条语义段落 | 耗时: {elapsed:.2f}s")

if __name__ == "__main__":
    transcriber = WhisperTranscriber()
    transcriber.process_all(force_reprocess=False)