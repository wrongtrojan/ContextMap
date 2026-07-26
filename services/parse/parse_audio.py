"""
录音解析库：faster-whisper 转录 → meta / middle 落盘。

推荐入口：
  python -m services.parse.parse_assets --scan
  python -m services.parse.parse_audio --input path/to/file.m4a

本模块仅处理 raw/audio 下的纯录音文件，不含视频提音。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROCESSED_AUDIO_DIR, PROJECT_ROOT, RAW_AUDIO_DIR
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

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}

WHISPER_MARKERS = ("model.bin", "config.json")


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
    whisper: WhisperConfig

    def to_fingerprint_dict(self) -> dict[str, Any]:
        return {
            "modality": "audio",
            "whisper": {
                "model_dir": self.whisper.model_dir,
                "modelscope_repo": self.whisper.modelscope_repo,
                "language": self.whisper.language,
                "beam_size": self.whisper.beam_size,
                "initial_prompt": self.whisper.initial_prompt,
            },
        }


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


def _build_settings() -> ParseSettings:
    data = _load_contextmap()
    return ParseSettings(whisper=_build_whisper_config(data.get("whisper")))


def _output_paths(out_root: Path, stem: str) -> dict[str, Path]:
    final_dir = out_root / stem
    return {
        "dir": final_dir,
        "md": final_dir / f"{stem}.md",
        "middle": final_dir / f"{stem}_middle.json",
        "meta": final_dir / META_FILENAME,
        "staging": out_root / f".{stem}.staging",
    }


def _outputs_complete(paths: dict[str, Path]) -> bool:
    if not paths["md"].is_file() or paths["md"].stat().st_size == 0:
        return False
    return paths["middle"].is_file() and paths["middle"].stat().st_size > 0


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


def collect_audio(input_arg: Path | None) -> list[Path]:
    def _scan_dir(directory: Path) -> list[Path]:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            return []
        return [
            path
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ]

    if input_arg is None:
        found = _scan_dir(RAW_AUDIO_DIR)
        if not found:
            raise FileNotFoundError(f"未指定 --input，且默认目录为空: audio: {RAW_AUDIO_DIR}")
        return found

    input_arg = input_arg.expanduser().resolve()
    if input_arg.is_dir():
        found = [
            path
            for path in sorted(input_arg.iterdir())
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not found:
            raise FileNotFoundError(f"目录下没有可识别的录音文件: {input_arg}")
        return found

    if not input_arg.exists():
        raise FileNotFoundError(f"文件不存在: {input_arg}")
    if input_arg.suffix.lower() not in AUDIO_EXTENSIONS:
        if input_arg.suffix.lower() in VIDEO_EXTENSIONS:
            raise ValueError(
                f"录音目录不接受视频容器: {input_arg}\n"
                "请先将视频转为 .m4a/.mp3 等纯音频文件后再 parse"
            )
        raise ValueError(f"不支持的录音格式: {input_arg}")
    return [input_arg]


def _segments_to_middle(segments: list[WhisperSegment]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        }
        for index, seg in enumerate(segments)
    ]


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
) -> None:
    payload = {
        "modality": "audio",
        "language": language,
        "duration": duration,
        "segments": _segments_to_middle(segments),
        "images": [],
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

    if not _outputs_complete(staging_paths):
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise RuntimeError("staging 产物校验失败，已回滚")

    meta = {
        "status": "success",
        "modality": "audio",
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
    out_root: Path,
    *,
    force: bool = False,
    allow_download: bool = True,
    dry_run: bool = False,
) -> tuple[Path, Path, str, dict[str, Any] | None]:
    settings = _build_settings()
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

    try:
        print("  [Stage 1] Whisper 转录...")
        segments, language, duration = _transcribe(
            source_path,
            settings.whisper,
            allow_download=allow_download,
        )

        md_path = staging_dir / f"{stem}.md"
        middle_path = staging_dir / f"{stem}_middle.json"
        _write_transcript_md(segments, md_path)
        _write_middle_json(
            middle_path,
            language=language,
            duration=duration,
            segments=segments,
        )

        outputs: dict[str, Any] = {
            "transcript_md": f"{stem}.md",
            "middle_json": f"{stem}_middle.json",
        }
        stats: dict[str, Any] = {
            "duration_sec": duration,
            "segment_count": len(segments),
            "language": language,
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

    parser = argparse.ArgumentParser(description="Audio-only wrapper for parse_assets")
    parser.add_argument("--input", default=None, help="录音文件或目录；省略则扫描 raw/audio")
    parser.add_argument("--out-audio", default=str(PROCESSED_AUDIO_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_arg = Path(args.input) if args.input else None
    sources = collect_audio(input_arg)
    out_audio = Path(args.out_audio).expanduser().resolve()
    items = [(path, "audio") for path in sources]

    from services.parse.parse_pdf import default_paths, mineru_defaults

    _, processed_pdf = default_paths()
    result = run_parse(
        items,
        out_pdf=processed_pdf,
        out_video=PROCESSED_AUDIO_DIR,
        out_audio=out_audio,
        mineru_defaults=mineru_defaults(),
        force=args.force,
        dry_run=args.dry_run,
        continue_on_error=False,
        allow_download=not args.no_download,
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
