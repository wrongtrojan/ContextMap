import cv2
import yaml
import os
import sys
import subprocess
from pathlib import Path
import time
import logging

# ================= 日志配置 =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [VideoSlicer] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class VideoSlicer:
    def __init__(self, global_cfg_path="configs/model_config.yaml", video_cfg_path="configs/video_config.yaml"):
        # 1. 定位项目根目录
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        # 2. 加载配置
        try:
            with open(self.project_root / global_cfg_path, 'r', encoding='utf-8') as f:
                self.g_cfg = yaml.safe_load(f)
            with open(self.project_root / video_cfg_path, 'r', encoding='utf-8') as f:
                self.v_cfg = yaml.safe_load(f)['slicer']
            logger.info("成功读取全局及视频配置。")
        except Exception as e:
            logger.error(f"配置文件加载失败，请检查路径: {e}")
            sys.exit(1)
            
        # 3. 初始化路径
        self.raw_video_dir = Path(self.g_cfg['paths']['raw_storage']) / "video"
        self.processed_dir = Path(self.g_cfg['paths']['processed_storage']) / "video"
        
        self.raw_video_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _should_process(self, video_path):
        """增量检查逻辑"""
        video_id = video_path.stem
        target_folder = self.processed_dir / video_id
        standard_mp4 = target_folder / f"{video_id}.standard.mp4"
        frames_dir = target_folder / "frames"
        
        # 检查关键产出是否存在且文件夹不为空
        exists = standard_mp4.exists() and frames_dir.exists() and len(list(frames_dir.glob("*.jpg"))) > 0
        if exists:
            logger.info(f"==== [SKIP] 增量跳过: {video_id} 已存在处理结果 ====")
        return not exists

    def _preprocess_video(self, input_path):
        """FFmpeg 标准化转码"""
        video_id = input_path.stem
        output_folder = self.processed_dir / video_id
        output_folder.mkdir(parents=True, exist_ok=True)
        output_mp4 = output_folder / f"{video_id}.standard.mp4"
        
        if output_mp4.exists():
            return output_mp4

        logger.info(f"--- [步骤1] 标准化转码: {input_path.name} ---")
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-c:v', 'libx264', '-preset', 'superfast', '-crf', '23',
            '-c:a', 'aac', '-ar', '16000', '-ac', '1',
            '-movflags', '+faststart',
            str(output_mp4)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return output_mp4
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 转码失败: {e.stderr.decode()}")
            return None

    def _save_uniform_frames(self, video_path, frame_dir, target_count):
        """均分补偿逻辑：处理静止页面"""
        logger.warning(f"--- [补偿启动] --- 关键帧密度不足，正在补充至约 {target_count} 帧")
        cap = cv2.VideoCapture(str(video_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        if total_frames <= 0 or fps <= 0: return

        # 步长计算
        step = total_frames // target_count
        if step <= 0: step = 1
        
        saved_count = 0
        for i in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = i / fps
            # 避开已有的语义切片（1.5秒间隔容差，防止PPT翻页处重复保存）
            if not any(abs(float(f.stem.split('_')[1]) - timestamp) < 1.5 for f in frame_dir.glob("time_*.jpg")):
                save_path = frame_dir / f"uniform_{timestamp:.2f}.jpg"
                cv2.imwrite(str(save_path), frame)
                saved_count += 1
            
            if saved_count >= target_count: break
            
        cap.release()
        logger.info(f"均分补偿完成：成功补拍 {saved_count} 张采样帧。")

    def process_single_video(self, video_path):
        """单视频核心处理流水线"""
        video_id = video_path.stem
        
        # 1. 转码
        standard_video = self._preprocess_video(video_path)
        if not standard_video: return
        
        # 2. 准备目录
        output_folder = self.processed_dir / video_id
        frame_dir = output_folder / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        # 3. 语义切片（滑动窗口）
        logger.info(f"--- [步骤2] 语义切片分析中: {video_id} ---")
        cap = cv2.VideoCapture(str(standard_video))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0
        
        last_saved_time = -self.v_cfg['min_interval']
        prev_gray = None
        count = 0
        saved_frames = 0
        start_t = time.time()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = count / fps
            # 抽样比对，减少CPU消耗
            if count % int(fps / self.v_cfg['sample_rate']) == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)
                
                if prev_gray is not None:
                    diff = cv2.absdiff(prev_gray, gray)
                    score = diff.mean() / 255.0
                    if score > self.v_cfg['frame_diff_threshold'] and (timestamp - last_saved_time) > self.v_cfg['min_interval']:
                        save_path = frame_dir / f"time_{timestamp:.2f}.jpg"
                        cv2.imwrite(str(save_path), frame)
                        last_saved_time = timestamp
                        saved_frames += 1
                prev_gray = gray
            count += 1
        cap.release()

        # 4. 密度评估与动态补偿
        # 逻辑：4分钟(240s)要求30帧 -> 0.125 帧/秒
        min_density = 0.125
        expected_min = max(int(duration_sec * min_density), 5) # 至少5帧兜底

        if saved_frames < expected_min:
            logger.warning(f"检测到静止画面过多：语义切片仅 {saved_frames} 帧，低于学术大纲要求 ({expected_min} 帧)")
            self._save_uniform_frames(standard_video, frame_dir, target_count=expected_min)
        else:
            logger.info(f"切片密度达标：语义切片共提取 {saved_frames} 帧关键图像。")

        logger.info(f"视频 [{video_id}] 处理完毕，总耗时: {time.time() - start_t:.2f}s")

    def run_batch(self):
        """批处理入口"""
        valid_exts = ('.mp4', '.mkv', '.avi', '.mov', '.flv')
        video_files = [f for f in self.raw_video_dir.iterdir() if f.suffix.lower() in valid_exts]
        
        if not video_files:
            logger.warning(f"未在目录 {self.raw_video_dir} 发现可处理视频。")
            return

        logger.info(f"========= 启动视频切片流水线 (共 {len(video_files)} 个任务) =========")
        for v_file in video_files:
            if self._should_process(v_file):
                try:
                    self.process_single_video(v_file)
                except Exception as e:
                    logger.error(f"处理任务 [{v_file.name}] 发生异常: {e}")
        logger.info("========= 所有任务处理结束 =========")

if __name__ == "__main__":
    slicer = VideoSlicer()
    slicer.run_batch()
    