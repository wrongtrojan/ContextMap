"""
MinerU PDF 解析库。

推荐入口：
  python -m services.parse.parse_assets --scan
  python -m services.parse.parse_assets --input path/to/file.pdf

本模块提供 `parse_one()` 供 parse_assets 调用；`main()` 为 PDF-only 薄封装。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from paths import CONTEXTMAP_CONFIG, PROCESSED_PDF_DIR, RAW_PDF_DIR
from services.parse.asset_coverage import pdf_coverage_from_middle
from services.parse.fingerprint import (
    META_FILENAME,
    PDF_FINGERPRINT_KEYS,
    atomic_replace_staging,
    build_pdf_fingerprint,
    load_meta,
    should_skip,
    utc_now_iso,
    write_failed_meta,
)


def default_paths() -> tuple[Path, Path]:
    return RAW_PDF_DIR, PROCESSED_PDF_DIR


def _load_contextmap() -> dict[str, Any]:
    if not CONTEXTMAP_CONFIG.exists():
        return {}
    with CONTEXTMAP_CONFIG.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_config(lang: str, backend: str, parse_method: str) -> dict[str, str]:
    return {
        "lang": lang,
        "backend": backend,
        "parse_method": parse_method,
    }


def mineru_defaults() -> dict[str, str]:
    data = _load_contextmap()
    mineru = ((data.get("parse") or {}).get("pdf") or {}).get("mineru") or {}
    return {
        "lang": str(mineru.get("lang", "ch")),
        "backend": str(mineru.get("backend", "pipeline")),
        "parse_method": str(mineru.get("parse_method", "auto")),
    }


def _import_do_parse():
    try:
        from mineru.cli.common import do_parse

        return do_parse
    except ImportError as e:
        raise RuntimeError(
            '无法导入 MinerU SDK，请先安装: pip install -U "mineru[all]"'
        ) from e


def output_paths(out_root: Path, stem: str) -> dict[str, Path]:
    final_dir = out_root / stem
    return {
        "dir": final_dir,
        "md": final_dir / f"{stem}.md",
        "middle": final_dir / f"{stem}_middle.json",
        "meta": final_dir / META_FILENAME,
        "images": final_dir / "images",
        "staging": out_root / f".{stem}.staging",
    }


def _outputs_complete(paths: dict[str, Path]) -> bool:
    if not paths["md"].is_file() or paths["md"].stat().st_size == 0:
        return False
    if not paths["middle"].is_file() or paths["middle"].stat().st_size == 0:
        return False
    return True


def evaluate_skip(
    pdf_path: Path,
    out_root: Path,
    config: dict[str, str],
    *,
    force: bool,
) -> tuple[bool, dict[str, Path], dict[str, Any] | None, str, dict[str, Any]]:
    paths = output_paths(out_root, pdf_path.stem)
    stored_fp = (load_meta(paths["meta"]) or {}).get("fingerprint")
    fingerprint = build_pdf_fingerprint(pdf_path, config, stored=stored_fp)
    skip, meta, reason = should_skip(
        paths["meta"],
        current_fingerprint=fingerprint,
        match_keys=PDF_FINGERPRINT_KEYS,
        outputs_complete=lambda: _outputs_complete(paths),
        force=force,
    )
    return skip, paths, meta, reason, fingerprint


def collect_pdfs(pdf_arg: Path | None, raw_dir: Path | None = None) -> list[Path]:
    """收集待解析 PDF 列表。"""
    search_dir = raw_dir or RAW_PDF_DIR
    if pdf_arg is None:
        if not search_dir.exists():
            search_dir.mkdir(parents=True, exist_ok=True)
            raise FileNotFoundError(
                f"未指定 --pdf，且默认输入目录为空: {search_dir}\n"
                f"请将 PDF 放入该目录，或使用: python -m services.parse.parse_assets --input <path>"
            )
        pdfs = sorted(search_dir.glob("*.pdf"))
        if not pdfs:
            raise FileNotFoundError(
                f"默认输入目录下没有 PDF 文件: {search_dir}\n"
                f"请放入 PDF 或使用: python -m services.parse.parse_assets --input <path>"
            )
        return pdfs

    pdf_arg = pdf_arg.expanduser().resolve()
    if pdf_arg.is_dir():
        pdfs = sorted(pdf_arg.glob("*.pdf"))
        if not pdfs:
            raise FileNotFoundError(f"目录下没有 PDF: {pdf_arg}")
        return pdfs
    if pdf_arg.suffix.lower() != ".pdf":
        raise ValueError(f"不是 PDF 文件: {pdf_arg}")
    if not pdf_arg.exists():
        raise FileNotFoundError(f"PDF 不存在: {pdf_arg}")
    return [pdf_arg]


def _run_mineru(
    do_parse,
    pdf_path: Path,
    work_dir: Path,
    *,
    lang: str,
    backend: str,
    parse_method: str,
) -> Path:
    """
    调用 MinerU 解析单个 PDF。
    MinerU 原始输出路径: {work_dir}/{pdf_filename}/{parse_method}/
    返回该目录 Path。
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = pdf_path.read_bytes()
    pdf_file_name = pdf_path.name

    do_parse(
        output_dir=str(work_dir),
        pdf_file_names=[pdf_file_name],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=[lang],
        backend=backend,
        parse_method=parse_method,
        formula_enable=True,
        table_enable=True,
        f_dump_md=True,
        f_dump_middle_json=True,
        f_dump_content_list=False,
        f_dump_model_output=False,
        f_draw_layout_bbox=False,
        f_draw_span_bbox=False,
        f_dump_orig_pdf=False,
    )

    parse_dir = work_dir / pdf_file_name / parse_method
    if not parse_dir.exists():
        candidates = list(work_dir.rglob("*_middle.json"))
        if not candidates:
            raise RuntimeError(
                f"MinerU 解析完成但未找到输出目录: {parse_dir}\n"
                f"请检查 MinerU 日志。"
            )
        parse_dir = candidates[0].parent

    return parse_dir


def _consolidate_output(
    parse_dir: Path,
    pdf_path: Path,
    paths: dict[str, Path],
    fingerprint: dict[str, Any],
    *,
    mineru_raw_dir: str,
) -> tuple[Path, Path, dict[str, Any]]:
    """
    将 MinerU 输出写入 staging 目录，校验通过后原子替换 final 目录。
    """
    stem = pdf_path.stem
    staging_dir = paths["staging"]
    final_dir = paths["dir"]

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    md_src = parse_dir / f"{pdf_path.name}.md"
    middle_src = parse_dir / f"{pdf_path.name}_middle.json"

    if not md_src.exists():
        md_candidates = list(parse_dir.glob("*.md"))
        if not md_candidates:
            raise RuntimeError(f"未找到 Markdown: {parse_dir}")
        md_src = md_candidates[0]

    if not middle_src.exists():
        middle_candidates = list(parse_dir.glob("*_middle.json"))
        if not middle_candidates:
            raise RuntimeError(f"未找到 middle.json: {parse_dir}")
        middle_src = middle_candidates[0]

    md_dst = staging_dir / f"{stem}.md"
    middle_dst = staging_dir / f"{stem}_middle.json"
    shutil.copy2(md_src, md_dst)
    shutil.copy2(middle_src, middle_dst)

    images_src = parse_dir / "images"
    if images_src.exists() and any(images_src.iterdir()):
        shutil.copytree(images_src, staging_dir / "images")

    stats = pdf_coverage_from_middle(middle_dst)
    meta = {
        "status": "success",
        "parsed_at": utc_now_iso(),
        "fingerprint": fingerprint,
        "outputs": {
            "markdown": f"{stem}.md",
            "middle_json": f"{stem}_middle.json",
            "images_dir": "images" if (staging_dir / "images").exists() else None,
        },
        "stats": stats,
        "mineru_raw_dir": mineru_raw_dir,
    }
    (staging_dir / META_FILENAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    staging_paths = {
        "dir": staging_dir,
        "md": md_dst,
        "middle": middle_dst,
        "meta": staging_dir / META_FILENAME,
        "images": staging_dir / "images",
        "staging": staging_dir,
    }
    if not _outputs_complete(staging_paths):
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise RuntimeError("staging 产物校验失败，已回滚")

    atomic_replace_staging(staging_dir, final_dir, stem)

    final_paths = output_paths(final_dir.parent, stem)
    return final_paths["middle"], final_paths["md"], stats


def parse_one(
    pdf_path: Path,
    out_root: Path,
    *,
    lang: str = "ch",
    backend: str = "pipeline",
    parse_method: str = "auto",
    keep_raw: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[Path, Path, str, dict[str, Any] | None]:
    """
    解析单个 PDF。
    返回: (middle_json_path, markdown_path, status, coverage)
    status: "skipped" | "parsed" | "dry_run"
    """
    config = _parse_config(lang, backend, parse_method)
    skip, paths, _meta, reason, fingerprint = evaluate_skip(
        pdf_path, out_root, config, force=force
    )

    if dry_run:
        action = "dry_run_skip" if skip else "dry_run_parse"
        coverage = None
        if skip and paths["middle"].is_file():
            coverage = pdf_coverage_from_middle(paths["middle"])
        return paths["middle"], paths["md"], action, coverage

    if skip:
        print(f"  [跳过] 已存在且指纹一致 ({reason})")
        coverage = pdf_coverage_from_middle(paths["middle"]) if paths["middle"].is_file() else None
        return paths["middle"], paths["md"], "skipped", coverage

    if reason != "force":
        print(f"  [重解析] 原因: {reason}")

    work_dir = out_root / "_mineru_work"

    try:
        do_parse = _import_do_parse()
        parse_dir = _run_mineru(
            do_parse,
            pdf_path,
            work_dir,
            lang=lang,
            backend=backend,
            parse_method=parse_method,
        )
        middle_dst, md_dst, stats = _consolidate_output(
            parse_dir,
            pdf_path,
            output_paths(out_root, pdf_path.stem),
            fingerprint,
            mineru_raw_dir=str(parse_dir),
        )
        print(f"  action=parsed pages={stats.get('pages')} text={stats.get('text_blocks')} "
              f"table={stats.get('table_blocks')}")
        print(f"  coverage: {json.dumps(stats, ensure_ascii=False)}")
        return middle_dst, md_dst, "parsed", stats
    except Exception as exc:
        write_failed_meta(paths["meta"], fingerprint, str(exc))
        raise
    finally:
        if not keep_raw:
            raw_parent = work_dir / pdf_path.name
            if raw_parent.exists():
                shutil.rmtree(raw_parent, ignore_errors=True)


def main() -> int:
    from services.parse.parse_assets import run_parse

    defaults = mineru_defaults()
    raw_dir, processed_dir = default_paths()

    parser = argparse.ArgumentParser(description="PDF-only wrapper for parse_assets")
    parser.add_argument("--pdf", default=None, help=f"PDF 文件或目录；省略则扫描 {raw_dir}")
    parser.add_argument("--out", default=str(processed_dir), help=f"输出目录（默认: {processed_dir}）")
    parser.add_argument("--lang", default=defaults["lang"])
    parser.add_argument("--backend", default=defaults["backend"], choices=["pipeline", "hybrid-auto-engine"])
    parser.add_argument("--parse-method", default=defaults["parse_method"], choices=["auto", "txt", "ocr"])
    parser.add_argument("--keep-raw", action="store_true", help="保留 _mineru_work/ 原始输出（调试用）")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    pdf_arg = Path(args.pdf) if args.pdf else None
    pdfs = collect_pdfs(pdf_arg, raw_dir=raw_dir)
    out_root = Path(args.out).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    mineru_cfg = {
        "lang": args.lang,
        "backend": args.backend,
        "parse_method": args.parse_method,
    }
    items = [(path, "pdf") for path in pdfs]
    result = run_parse(
        items,
        out_pdf=out_root,
        out_video=PROCESSED_PDF_DIR,
        out_audio=PROCESSED_PDF_DIR,
        mineru_defaults=mineru_cfg,
        force=args.force,
        dry_run=False,
        continue_on_error=False,
        allow_download=True,
        keep_raw=args.keep_raw,
    )
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
