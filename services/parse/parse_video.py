"""
视频解析库：FFmpeg 转码 + OpenCV 抽帧 + faster-whisper 转录。

推荐入口：
  python -m services.parse.parse_assets --scan
  python -m services.parse.parse_assets --input path/to/file.mp4

本模块仅处理 video；录音请使用 parse_audio。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from paths import (
    CONTEXTMAP_CONFIG,
    PROCESSED_PDF_DIR,
    PROCESSED_VIDEO_DIR,
    PROJECT_ROOT,
    RAW_VIDEO_DIR,
)

from services.parse.asset_coverage import media_coverage_from_middle
from services.parse.fingerprint import (
    META_FILENAME,
    MEDIA_FINGERPRINT_KEYS,
    atomic_replace_staging,
    build_media_fingerprint,
    load_meta,
    should_skip,
    utc_now_iso,
    write_failed_meta,
)
from services.parse.whisper_runtime import WhisperRuntimeConfig, WhisperSegment, transcribe_media

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}

WHISPER_MARKERS = ("model.bin", "config.json")

@dataclass
class SlicerConfig:
    frame_diff_threshold: float = 0.03
    sample_rate: float = 2.0
    min_interval: float = 10.0


@dataclass
class WhisperConfig:
    model_dir: str = "models/whisper_v3"
    modelscope_repo: str = "Systran/faster-whisper-large-v3"
    language: str = "zh"
    beam_size: int = 5
    initial_prompt: str = (
        "这是一段学术讲解。请使用简体中文转录，确保专业术语（如算法、模型、参数等）准确。"
    )

    def to_runtime_config(self) -> WhisperRuntimeConfig:
        return WhisperRuntimeConfig(
            model_dir=self.model_dir,
            modelscope_repo=self.modelscope_repo,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
        )


@dataclass
class ParseSettings:
    ffmpeg_preset: str = "fast"
    ffmpeg_crf: int = 23
    slicer: SlicerConfig | None = None
    whisper: WhisperConfig | None = None

    def to_fingerprint_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "modality": "video",
            "ffmpeg_preset": self.ffmpeg_preset,
            "ffmpeg_crf": self.ffmpeg_crf,
        }
        if self.slicer is not None:
            data["slicer"] = {
                "frame_diff_threshold": self.slicer.frame_diff_threshold,
                "sample_rate": self.slicer.sample_rate,
                "min_interval": self.slicer.min_interval,
            }
        if self.whisper is not None:
            data["whisper"] = {
                "model_dir": self.whisper.model_dir,
                "modelscope_repo": self.whisper.modelscope_repo,
                "language": self.whisper.language,
                "beam_size": self.whisper.beam_size,
                "initial_prompt": self.whisper.initial_prompt,
            }
        return data


@dataclass
class FrameInfo:
    filename: str
    timestamp: float
    path: str


def _check_gpu() -> tuple[str, bool]:
    """检测 GPU；驱动/硬件不兼容时回退 CPU（避免误报 CUDA 可用）。"""
    try:
        import torch

        if not torch.cuda.is_available():
            return "CPU", False
        try:
            name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            return f"CUDA ({name}, {vram_gb:.1f} GB)", True
        except Exception as exc:
            return f"CPU (CUDA 初始化失败: {exc})", False
    except ImportError:
        pass
    return "CPU", False


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未找到 ffmpeg，请先安装并加入 PATH")


def _load_contextmap() -> dict[str, Any]:
    if not CONTEXTMAP_CONFIG.exists():
        return {}
    with CONTEXTMAP_CONFIG.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _build_whisper_config(raw: dict[str, Any] | None = None) -> WhisperConfig:
    raw = raw or {}
    defaults = WhisperConfig()
    return WhisperConfig(
        model_dir=str(raw.get("model_dir", defaults.model_dir)),
        modelscope_repo=str(raw.get("modelscope_repo", defaults.modelscope_repo)),
        language=str(raw.get("language", defaults.language)),
        beam_size=int(raw.get("beam_size", defaults.beam_size)),
        initial_prompt=str(raw.get("initial_prompt", defaults.initial_prompt)),
    )


def _build_slicer_config(raw: dict[str, Any] | None = None) -> SlicerConfig:
    raw = raw or {}
    defaults = SlicerConfig()
    return SlicerConfig(
        frame_diff_threshold=float(raw.get("frame_diff_threshold", defaults.frame_diff_threshold)),
        sample_rate=float(raw.get("sample_rate", defaults.sample_rate)),
        min_interval=float(raw.get("min_interval", defaults.min_interval)),
    )


def _build_settings() -> ParseSettings:
    data = _load_contextmap()
    video_cfg = (data.get("parse") or {}).get("video") or {}
    ffmpeg_cfg = video_cfg.get("ffmpeg") or {}
    return ParseSettings(
        ffmpeg_preset=str(ffmpeg_cfg.get("preset", "fast")),
        ffmpeg_crf=int(ffmpeg_cfg.get("crf", 23)),
        slicer=_build_slicer_config(video_cfg.get("slicer")),
        whisper=_build_whisper_config(data.get("whisper")),
    )


def _whisper_model_dir(config: WhisperConfig) -> Path:
    model_path = Path(config.model_dir)
    if model_path.is_absolute():
        return model_path
    return PROJECT_ROOT / model_path


def _is_whisper_model_ready(model_dir: Path) -> bool:
    return model_dir.is_dir() and any((model_dir / marker).exists() for marker in WHISPER_MARKERS)


def _ensure_whisper_model(model_dir: Path, repo: str, *, allow_download: bool) -> Path:
    if _is_whisper_model_ready(model_dir):
        return model_dir
    if not allow_download:
        raise RuntimeError(
            f"Whisper 模型不存在: {model_dir}\n"
            "请去掉 --no-download 重新运行以自动下载，或执行: bash models/downloader.sh"
        )
    print(f"[下载] Whisper 模型不存在，正在从 ModelScope 下载到 {model_dir} ...")
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "自动下载 Whisper 需要 modelscope: pip install modelscope"
        ) from exc
    snapshot_download(repo, local_dir=str(model_dir))
    if not _is_whisper_model_ready(model_dir):
        raise RuntimeError(f"Whisper 模型下载后校验失败: {model_dir}")
    print(f"[下载] 完成: {model_dir}")
    return model_dir


def _output_paths(out_root: Path, stem: str) -> dict[str, Path]:
    final_dir = out_root / stem
    return {
        "dir": final_dir,
        "md": final_dir / f"{stem}.md",
        "middle": final_dir / f"{stem}_middle.json",
        "meta": final_dir / META_FILENAME,
        "images": final_dir / "images",
        "standard_video": final_dir / f"{stem}.standard.mp4",
        "staging": out_root / f".{stem}.staging",
    }


def _outputs_complete(paths: dict[str, Path]) -> bool:
    if not paths["md"].is_file() or paths["md"].stat().st_size == 0:
        return False
    if not paths["middle"].is_file() or paths["middle"].stat().st_size == 0:
        return False
    images_dir = paths["images"]
    if not images_dir.is_dir():
        return False
    return any(images_dir.glob("*.jpg"))


def evaluate_skip(
    source_path: Path,
    out_root: Path,
    settings: ParseSettings,
    *,
    force: bool,
) -> tuple[bool, dict[str, Path], dict[str, Any] | None, str, dict[str, Any]]:
    paths = _output_paths(out_root, source_path.stem)
    stored_fp = (load_meta(paths["meta"]) or {}).get("fingerprint")
    fingerprint = build_media_fingerprint(source_path, settings.to_fingerprint_dict(), stored=stored_fp)
    skip, meta, reason = should_skip(
        paths["meta"],
        current_fingerprint=fingerprint,
        match_keys=MEDIA_FINGERPRINT_KEYS,
        outputs_complete=lambda: _outputs_complete(paths),
        force=force,
    )
    return skip, paths, meta, reason, fingerprint


def collect_media(input_arg: Path | None) -> list[Path]:
    def _scan_dir(directory: Path) -> list[Path]:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            return []
        return [
            path
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]

    if input_arg is None:
        found = _scan_dir(RAW_VIDEO_DIR)
        if not found:
            raise FileNotFoundError(f"未指定 --input，且默认目录为空: video: {RAW_VIDEO_DIR}")
        return found

    input_arg = input_arg.expanduser().resolve()
    if input_arg.is_dir():
        found = [
            path
            for path in sorted(input_arg.iterdir())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not found:
            raise FileNotFoundError(f"目录下没有可识别的视频文件: {input_arg}")
        return found

    if not input_arg.exists():
        raise FileNotFoundError(f"文件不存在: {input_arg}")
    if input_arg.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"不支持的视频格式: {input_arg}")
    return [input_arg]


def _standardize_video(raw_path: Path, dst: Path, *, preset: str, crf: int) -> None:
    _require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 转码失败:\n{result.stderr[-2000:]}")


def _save_uniform_frames(
    cap: Any,
    frame_dir: Path,
    target_count: int,
    fps: float,
    total_frames: int,
) -> int:
    import cv2

    step = max(total_frames // target_count, 1)
    saved_count = 0
    for index in range(0, total_frames, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = cap.read()
        if not ret or saved_count >= target_count:
            break
        timestamp = index / fps
        cv2.imwrite(str(frame_dir / f"time_{timestamp:.2f}.jpg"), frame)
        saved_count += 1
    return saved_count


def _extract_frames(
    standard_video: Path,
    images_dir: Path,
    slicer: SlicerConfig,
) -> list[FrameInfo]:
    import cv2

    images_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(standard_video))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {standard_video}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    prev_gray = None
    last_saved_time = -slicer.min_interval
    saved_count = 0
    frame_step = max(int(fps / slicer.sample_rate), 1)

    for index in range(0, total_frames, frame_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = index / fps
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)

        should_save = False
        if prev_gray is None:
            should_save = True
        else:
            score = cv2.absdiff(prev_gray, gray).mean() / 255.0
            if score > slicer.frame_diff_threshold and (timestamp - last_saved_time) > slicer.min_interval:
                should_save = True

        if should_save:
            filename = f"time_{timestamp:.2f}.jpg"
            cv2.imwrite(str(images_dir / filename), frame)
            last_saved_time = timestamp
            saved_count += 1

        prev_gray = gray

    min_expected = max(int(duration * (1 / 15)), 5)
    if saved_count < min_expected:
        print(f"  [抽帧] 密度偏低 ({saved_count}/{min_expected})，启用均匀补帧")
        saved_count = _save_uniform_frames(cap, images_dir, min_expected, fps, total_frames)
    else:
        print(f"  [抽帧] 语义抽帧完成: {saved_count} 帧")

    cap.release()

    frames: list[FrameInfo] = []
    for image_path in sorted(images_dir.glob("time_*.jpg")):
        match = re.match(r"time_([0-9.]+)\.jpg$", image_path.name)
        timestamp = float(match.group(1)) if match else 0.0
        frames.append(
            FrameInfo(
                filename=image_path.name,
                timestamp=timestamp,
                path=f"images/{image_path.name}",
            )
        )
    return frames


def _transcribe(
    media_path: Path,
    config: WhisperConfig,
    *,
    allow_download: bool,
) -> tuple[list[WhisperSegment], str, float]:
    return transcribe_media(
        media_path,
        config.to_runtime_config(),
        allow_download=allow_download,
    )


def _link_segments_to_images(
    segments: list[WhisperSegment],
    frames: list[FrameInfo],
) -> list[dict[str, Any]]:
    if not frames:
        return [
            {
                "index": index,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            }
            for index, seg in enumerate(segments)
        ]

    linked: list[dict[str, Any]] = []
    for index, seg in enumerate(segments):
        candidates = [frame for frame in frames if frame.timestamp <= seg.start + 0.001]
        nearest = candidates[-1] if candidates else frames[0]
        linked.append(
            {
                "index": index,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "linked_images": [
                    {
                        "filename": nearest.filename,
                        "timestamp": nearest.timestamp,
                        "relation": "nearest_at_or_before",
                    }
                ],
            }
        )
    return linked


def _write_transcript_md(segments: list[WhisperSegment], md_path: Path) -> None:
    lines: list[str] = []
    for seg in segments:
        lines.append(f"<!-- {seg.start:.2f}-{seg.end:.2f} -->")
        lines.append(seg.text)
        lines.append("")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_middle_json(
    middle_path: Path,
    *,
    language: str,
    duration: float,
    segments: list[WhisperSegment],
    frames: list[FrameInfo],
) -> None:
    payload = {
        "modality": "video",
        "language": language,
        "duration": duration,
        "segments": _link_segments_to_images(segments, frames),
        "images": [
            {
                "filename": frame.filename,
                "timestamp": frame.timestamp,
                "path": frame.path,
            }
            for frame in frames
        ],
    }
    middle_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _finalize_output(
    staging_dir: Path,
    final_dir: Path,
    stem: str,
    fingerprint: dict[str, Any],
    stats: dict[str, Any],
    outputs: dict[str, Any],
) -> None:
    staging_paths = _output_paths(staging_dir.parent, stem)
    staging_paths["dir"] = staging_dir
    staging_paths["md"] = staging_dir / f"{stem}.md"
    staging_paths["middle"] = staging_dir / f"{stem}_middle.json"
    staging_paths["meta"] = staging_dir / META_FILENAME
    staging_paths["images"] = staging_dir / "images"
    staging_paths["standard_video"] = staging_dir / f"{stem}.standard.mp4"

    if not _outputs_complete(staging_paths):
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise RuntimeError("staging 产物校验失败，已回滚")

    meta = {
        "status": "success",
        "modality": "video",
        "parsed_at": utc_now_iso(),
        "fingerprint": fingerprint,
        "outputs": outputs,
        "stats": stats,
    }
    (staging_dir / META_FILENAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    atomic_replace_staging(staging_dir, final_dir, stem)


def parse_one(
    source_path: Path,
    out_video: Path,
    *,
    force: bool = False,
    allow_download: bool = True,
    skip_frames: bool = False,
    skip_transcribe: bool = False,
    dry_run: bool = False,
) -> tuple[Path, Path, str, dict[str, Any] | None]:
    settings = _build_settings()
    out_root = out_video
    out_root.mkdir(parents=True, exist_ok=True)

    skip, paths, _meta, reason, fingerprint = evaluate_skip(
        source_path, out_root, settings, force=force
    )

    if dry_run:
        action = "dry_run_skip" if skip else "dry_run_parse"
        coverage = None
        if skip and paths["middle"].is_file():
            coverage = media_coverage_from_middle(paths["middle"])
        return paths["middle"], paths["md"], action, coverage

    if skip:
        print(f"  [跳过] 已存在且指纹一致 ({reason})")
        coverage = (
            media_coverage_from_middle(paths["middle"]) if paths["middle"].is_file() else None
        )
        return paths["middle"], paths["md"], "skipped", coverage

    if reason != "force":
        print(f"  [重解析] 原因: {reason}")

    stem = source_path.stem
    staging_dir = paths["staging"]
    final_dir = paths["dir"]
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    frames: list[FrameInfo] = []
    segments: list[WhisperSegment] = []
    language = settings.whisper.language if settings.whisper else "zh"
    duration = 0.0
    transcribe_input = source_path

    try:
        assert settings.slicer is not None and settings.whisper is not None
        standard_video = staging_dir / f"{stem}.standard.mp4"
        images_dir = staging_dir / "images"

        print("  [Stage 1] FFmpeg 标准化...")
        _standardize_video(
            source_path,
            standard_video,
            preset=settings.ffmpeg_preset,
            crf=settings.ffmpeg_crf,
        )
        transcribe_input = standard_video

        if not skip_frames:
            print("  [Stage 2] OpenCV 抽帧...")
            frames = _extract_frames(standard_video, images_dir, settings.slicer)
        else:
            images_dir.mkdir(parents=True, exist_ok=True)

        if not skip_transcribe:
            print("  [Stage 3] Whisper 转录...")
            segments, language, duration = _transcribe(
                transcribe_input,
                settings.whisper,
                allow_download=allow_download,
            )
        else:
            raise RuntimeError("视频模态不能跳过转录")

        md_path = staging_dir / f"{stem}.md"
        middle_path = staging_dir / f"{stem}_middle.json"
        _write_transcript_md(segments, md_path)
        _write_middle_json(
            middle_path,
            language=language,
            duration=duration,
            segments=segments,
            frames=frames,
        )

        outputs: dict[str, Any] = {
            "transcript_md": f"{stem}.md",
            "middle_json": f"{stem}_middle.json",
            "images_dir": "images",
            "standard_video": f"{stem}.standard.mp4",
        }
        stats: dict[str, Any] = {
            "duration_sec": duration,
            "segment_count": len(segments),
            "language": language,
            "frame_count": len(frames),
        }

        _finalize_output(
            staging_dir,
            final_dir,
            stem,
            fingerprint,
            stats,
            outputs,
        )
        print(
            f"  action=parsed duration_sec={stats.get('duration_sec')} "
            f"segments={stats.get('segment_count')}"
        )
        print(f"  coverage: {json.dumps(stats, ensure_ascii=False)}")
    except Exception as exc:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        write_failed_meta(paths["meta"], fingerprint, str(exc))
        raise

    final_paths = _output_paths(out_root, stem)
    stats = media_coverage_from_middle(final_paths["middle"])
    return final_paths["middle"], final_paths["md"], "parsed", stats


def main() -> int:
    from services.parse.parse_assets import run_parse

    parser = argparse.ArgumentParser(description="Video-only wrapper for parse_assets")
    parser.add_argument("--input", default=None, help="视频文件或目录；省略则扫描 raw/video")
    parser.add_argument("--out-video", default=str(PROCESSED_VIDEO_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--skip-frames", action="store_true", help="跳过 OpenCV 抽帧（调试用）")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过 Whisper 转录（调试用）")
    args = parser.parse_args()

    input_arg = Path(args.input) if args.input else None
    sources = collect_media(input_arg)
    out_video = Path(args.out_video).expanduser().resolve()
    items = [(path, "video") for path in sources]

    from services.parse.parse_pdf import default_paths, mineru_defaults

    _, processed_pdf = default_paths()
    result = run_parse(
        items,
        out_pdf=processed_pdf,
        out_video=out_video,
        out_audio=PROCESSED_VIDEO_DIR,
        mineru_defaults=mineru_defaults(),
        force=args.force,
        dry_run=False,
        continue_on_error=False,
        allow_download=not args.no_download,
        skip_frames=args.skip_frames,
        skip_transcribe=args.skip_transcribe,
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
