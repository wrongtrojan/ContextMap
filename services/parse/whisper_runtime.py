"""Shared faster-whisper model singleton for parse_audio and parse_video."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paths import PROJECT_ROOT

WHISPER_MARKERS = ("model.bin", "config.json")
_WHISPER_MODEL: Any | None = None
_WHISPER_CACHE_KEY: tuple[str, str, str] | None = None
_WHISPER_LOCK = threading.Lock()


@dataclass
class WhisperRuntimeConfig:
    model_dir: str = "models/whisper_v3"
    modelscope_repo: str = "Systran/faster-whisper-large-v3"
    language: str = "zh"
    beam_size: int = 5
    initial_prompt: str = (
        "这是一段学术讲解。请使用简体中文转录，确保专业术语（如算法、模型、参数等）准确。"
    )


def whisper_model_dir(config: WhisperRuntimeConfig) -> Path:
    model_path = Path(config.model_dir)
    if model_path.is_absolute():
        return model_path
    return PROJECT_ROOT / model_path


def is_whisper_model_ready(model_dir: Path) -> bool:
    return model_dir.is_dir() and any((model_dir / marker).exists() for marker in WHISPER_MARKERS)


def ensure_whisper_model(model_dir: Path, repo: str, *, allow_download: bool) -> Path:
    if is_whisper_model_ready(model_dir):
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
        raise RuntimeError("自动下载 Whisper 需要 modelscope: pip install modelscope") from exc
    snapshot_download(repo, local_dir=str(model_dir))
    if not is_whisper_model_ready(model_dir):
        raise RuntimeError(f"Whisper 模型下载后校验失败: {model_dir}")
    print(f"[下载] 完成: {model_dir}")
    return model_dir


def check_gpu() -> tuple[str, bool]:
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


def get_whisper_model(config: WhisperRuntimeConfig, *, allow_download: bool) -> Any:
    global _WHISPER_MODEL, _WHISPER_CACHE_KEY
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("未安装 faster-whisper: pip install faster-whisper") from exc

    model_dir = ensure_whisper_model(
        whisper_model_dir(config),
        config.modelscope_repo,
        allow_download=allow_download,
    )
    _, use_cuda = check_gpu()
    device = "cuda" if use_cuda else "cpu"
    compute_type = "float16" if use_cuda else "int8"
    cache_key = (str(model_dir), device, compute_type)
    if _WHISPER_MODEL is not None and _WHISPER_CACHE_KEY == cache_key:
        return _WHISPER_MODEL

    print(f"  [Whisper] 加载模型: {model_dir} ({device}, {compute_type})")
    _WHISPER_MODEL = WhisperModel(
        str(model_dir),
        device=device,
        compute_type=compute_type,
        local_files_only=True,
    )
    _WHISPER_CACHE_KEY = cache_key
    return _WHISPER_MODEL


@dataclass
class WhisperSegment:
    start: float
    end: float
    text: str


def transcribe_media(
    media_path: Path,
    config: WhisperRuntimeConfig,
    *,
    allow_download: bool,
) -> tuple[list[WhisperSegment], str, float]:
    with _WHISPER_LOCK:
        model = get_whisper_model(config, allow_download=allow_download)
        print(f"  [Whisper] 开始转录: {media_path.name}")
        segments_iter, info = model.transcribe(
            str(media_path),
            beam_size=config.beam_size,
            language=config.language,
            vad_filter=True,
            initial_prompt=config.initial_prompt,
        )
        segments: list[WhisperSegment] = []
        for seg in segments_iter:
            text = seg.text.strip()
            if not text:
                continue
            segments.append(
                WhisperSegment(start=round(seg.start, 2), end=round(seg.end, 2), text=text)
            )
            if len(segments) % 20 == 0:
                print(f"  [Whisper] 进度: {seg.end:.1f}s / {info.duration:.1f}s, {len(segments)} 段")
        language = info.language or config.language
        duration = round(float(info.duration or 0.0), 2)
        print(f"  [Whisper] 完成: {len(segments)} 段, 时长 {duration}s, 语言 {language}")
        return segments, language, duration
