"""
Unified parse CLI for PDF, video, and audio assets.

Examples:
  python -m services.parse.parse_assets --scan
  python -m services.parse.parse_assets --input path/to/file.pdf
  python -m services.parse.parse_assets --force --continue-on-error
  python -m services.parse.parse_assets --scan --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from paths import (
    PROCESSED_AUDIO_DIR,
    PROCESSED_PDF_DIR,
    PROCESSED_VIDEO_DIR,
    RAW_AUDIO_DIR,
    RAW_PDF_DIR,
    RAW_VIDEO_DIR,
)
from services.parse.parse_audio import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS as AUDIO_VIDEO_EXTENSIONS,
    collect_audio,
    parse_one as parse_audio_one,
)
from services.parse.parse_pdf import (
    collect_pdfs,
    default_paths,
    mineru_defaults,
    parse_one as parse_pdf_one,
)
from services.parse.parse_video import (
    VIDEO_EXTENSIONS,
    collect_media,
    parse_one as parse_video_one,
)
from services.parse.types import ParseSummary


def _scan_all_raw() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []

    if RAW_PDF_DIR.exists():
        items.extend((path, "pdf") for path in sorted(RAW_PDF_DIR.glob("*.pdf")))

    if RAW_VIDEO_DIR.exists():
        items.extend(
            (path, "video")
            for path in sorted(RAW_VIDEO_DIR.iterdir())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        )

    if RAW_AUDIO_DIR.exists():
        items.extend(
            (path, "audio")
            for path in sorted(RAW_AUDIO_DIR.iterdir())
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        )

    return items


def _resolve_input(input_arg: Path | None, scan: bool) -> list[tuple[Path, str]]:
    if scan:
        items = _scan_all_raw()
        if not items:
            raise FileNotFoundError(
                f"--scan 未找到 raw 资产:\n"
                f"  pdf: {RAW_PDF_DIR}\n"
                f"  video: {RAW_VIDEO_DIR}\n"
                f"  audio: {RAW_AUDIO_DIR}"
            )
        return items

    if input_arg is None:
        raise ValueError("请指定 --input 或 --scan")

    input_arg = input_arg.expanduser().resolve()
    if input_arg.suffix.lower() == ".pdf":
        return [(input_arg, "pdf")]
    if input_arg.suffix.lower() in AUDIO_EXTENSIONS:
        return [(input_arg, "audio")]
    if input_arg.suffix.lower() in VIDEO_EXTENSIONS:
        if RAW_AUDIO_DIR in input_arg.parents or input_arg.parent.resolve() == RAW_AUDIO_DIR.resolve():
            raise ValueError(
                f"录音目录不接受视频容器: {input_arg}\n"
                "请先将视频转为 .m4a/.mp3 等纯音频文件后再 parse"
            )
        return [(input_arg, "video")]

    pdfs = collect_pdfs(input_arg)
    if pdfs:
        return [(path, "pdf") for path in pdfs]

    try:
        audio_paths = collect_audio(input_arg)
        if audio_paths:
            return [(path, "audio") for path in audio_paths]
    except (FileNotFoundError, ValueError):
        pass

    try:
        video_paths = collect_media(input_arg)
        if video_paths:
            return [(path, "video") for path in video_paths]
    except (FileNotFoundError, ValueError):
        pass

    if input_arg.suffix.lower() in AUDIO_VIDEO_EXTENSIONS:
        raise ValueError(
            f"录音目录不接受视频容器: {input_arg}\n"
            "请先将视频转为 .m4a/.mp3 等纯音频文件后再 parse"
        )

    raise FileNotFoundError(f"未识别可解析资产: {input_arg}")


def _run_one(
    source_path: Path,
    modality: str,
    *,
    out_pdf: Path,
    out_video: Path,
    out_audio: Path,
    mineru_defaults_cfg: dict[str, str],
    force: bool,
    dry_run: bool,
    allow_download: bool,
    keep_raw: bool,
    skip_frames: bool,
    skip_transcribe: bool,
) -> ParseSummary:
    try:
        if modality == "pdf":
            middle, md, status, coverage = parse_pdf_one(
                source_path,
                out_pdf,
                lang=mineru_defaults_cfg["lang"],
                backend=mineru_defaults_cfg["backend"],
                parse_method=mineru_defaults_cfg["parse_method"],
                force=force,
                dry_run=dry_run,
                keep_raw=keep_raw,
            )
        elif modality == "audio":
            middle, md, status, coverage = parse_audio_one(
                source_path,
                out_audio,
                force=force,
                dry_run=dry_run,
                allow_download=allow_download,
            )
        else:
            middle, md, status, coverage = parse_video_one(
                source_path,
                out_video,
                force=force,
                dry_run=dry_run,
                allow_download=allow_download,
                skip_frames=skip_frames,
                skip_transcribe=skip_transcribe,
            )

        if dry_run:
            skip_reason = "cache_hit" if status == "dry_run_skip" else "would_parse"
        else:
            skip_reason = "cache_hit" if status == "skipped" else None

        return ParseSummary(
            source_path=str(source_path),
            modality=modality,
            action=status,
            skip_reason=skip_reason,
            coverage=coverage or {},
            middle_path=str(middle) if middle else None,
            md_path=str(md) if md else None,
        )
    except Exception as exc:
        return ParseSummary(
            source_path=str(source_path),
            modality=modality,
            action="failed" if not dry_run else "dry_run_failed",
            error=str(exc),
        )


def run_parse(
    items: list[tuple[Path, str]],
    *,
    out_pdf: Path,
    out_video: Path,
    out_audio: Path,
    mineru_defaults: dict[str, str],
    force: bool,
    dry_run: bool,
    continue_on_error: bool,
    allow_download: bool,
    keep_raw: bool = False,
    skip_frames: bool = False,
    skip_transcribe: bool = False,
) -> dict[str, Any]:
    summaries: list[ParseSummary] = []
    parsed = skipped = failed = dry_run_count = 0

    for index, (source_path, modality) in enumerate(items, 1):
        print(f"\n[{index}/{len(items)}] ({modality}) {source_path.name}")
        summary = _run_one(
            source_path,
            modality,
            out_pdf=out_pdf,
            out_video=out_video,
            out_audio=out_audio,
            mineru_defaults_cfg=mineru_defaults,
            force=force,
            dry_run=dry_run,
            allow_download=allow_download,
            keep_raw=keep_raw,
            skip_frames=skip_frames,
            skip_transcribe=skip_transcribe,
        )
        summaries.append(summary)

        if summary.action == "parsed":
            parsed += 1
            print("  action=parsed")
        elif summary.action == "dry_run_parse":
            dry_run_count += 1
            print(f"  action=dry_run_parse reason={summary.skip_reason}")
        elif summary.action in {"skipped", "dry_run_skip"}:
            skipped += 1
            tag = "dry_run_skip" if dry_run else "skipped"
            print(f"  action={tag} reason={summary.skip_reason}")
        else:
            failed += 1
            print(f"  action=failed error={summary.error}")
            if not continue_on_error:
                break

        if summary.coverage:
            print(f"  coverage: {json.dumps(summary.coverage, ensure_ascii=False)}")
        if summary.middle_path:
            print(f"  middle: {summary.middle_path}")

    return {
        "parsed": parsed,
        "skipped": skipped,
        "failed": failed,
        "dry_run_would_parse": dry_run_count,
        "items": [item.to_dict() for item in summaries],
    }


def main() -> int:
    raw_pdf, processed_pdf = default_paths()
    defaults = mineru_defaults()

    parser = argparse.ArgumentParser(description="统一解析 raw PDF / video / audio 资产")
    parser.add_argument("--scan", action="store_true", help="扫描 raw/pdf、raw/video、raw/audio")
    parser.add_argument("--input", default=None, help="单个文件或目录")
    parser.add_argument("--out-pdf", default=str(processed_pdf), help="PDF 输出目录")
    parser.add_argument("--out-video", default=str(PROCESSED_VIDEO_DIR), help="视频输出目录")
    parser.add_argument("--out-audio", default=str(PROCESSED_AUDIO_DIR), help="音频输出目录")
    parser.add_argument("--force", action="store_true", help="强制重新解析")
    parser.add_argument("--continue-on-error", action="store_true", help="单文件失败不中断")
    parser.add_argument("--dry-run", action="store_true", help="仅 fingerprint 判定，不调用 MinerU/FFmpeg")
    parser.add_argument("--no-download", action="store_true", help="禁止自动下载 Whisper 模型")
    parser.add_argument("--keep-raw", action="store_true", help="保留 PDF _mineru_work/ 原始输出（调试用）")
    parser.add_argument("--skip-frames", action="store_true", help="跳过 OpenCV 抽帧（调试用）")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过 Whisper 转录（调试用）")
    args = parser.parse_args()

    if not args.scan and not args.input:
        parser.error("请指定 --scan 或 --input")

    input_arg = Path(args.input) if args.input else None
    items = _resolve_input(input_arg, scan=args.scan)

    out_pdf = Path(args.out_pdf).expanduser().resolve()
    out_video = Path(args.out_video).expanduser().resolve()
    out_audio = Path(args.out_audio).expanduser().resolve()
    out_pdf.mkdir(parents=True, exist_ok=True)
    out_video.mkdir(parents=True, exist_ok=True)
    out_audio.mkdir(parents=True, exist_ok=True)

    print(f"待处理: {len(items)} 个资产")
    print(f"raw pdf : {raw_pdf}")
    print(f"幂等: {'关闭 (--force)' if args.force else '开启'}")
    if args.dry_run:
        print("模式: dry-run（不调用解析引擎）")

    result = run_parse(
        items,
        out_pdf=out_pdf,
        out_video=out_video,
        out_audio=out_audio,
        mineru_defaults=defaults,
        force=args.force,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        allow_download=not args.no_download,
        keep_raw=args.keep_raw,
        skip_frames=args.skip_frames,
        skip_transcribe=args.skip_transcribe,
    )

    print(
        f"\n统计: parsed={result['parsed']} skipped={result['skipped']} "
        f"failed={result['failed']}"
    )
    if args.dry_run:
        print(f"dry-run would_parse={result['dry_run_would_parse']}")

    return 1 if result["failed"] and not args.continue_on_error else 0


if __name__ == "__main__":
    sys.exit(main())
