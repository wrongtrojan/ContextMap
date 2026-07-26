"""AutoRE Mistral-7B + QLoRA adapter singleton with lazy on-disk download."""

from __future__ import annotations

import json
import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from paths import PROJECT_ROOT

logger = logging.getLogger("AutoRERuntime")

Stage = Literal["relation", "head", "fact"]

# HF dante123/AutoRE: relation / subject / fact
_STAGE_DIR_NAMES: dict[Stage, str] = {
    "relation": "relation",
    "head": "subject",
    "fact": "fact",
}

_AUTORE_LOCK = threading.Lock()
_DOWNLOAD_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, Any] = {}
_TOKENIZER: Any | None = None
_CONFIG_KEY: tuple[str, ...] | None = None
_MANIFEST_NAME = "autore_manifest.json"


@dataclass
class AutoRERuntimeConfig:
    base_modelscope_repo: str = "AI-ModelScope/Mistral-7B-v0.1"
    adapter_repo: str = "dante123/AutoRE"
    model_dir: str = "models/autore"
    hf_endpoint: str | None = "https://hf-mirror.com"
    device: str = "cuda"
    load_in_4bit: bool = True
    max_new_tokens: int = 512


def config_from_yaml() -> AutoRERuntimeConfig:
    from services.kg.config import load_kg_config

    raw = load_kg_config().get("autore") or {}
    hf_endpoint = raw.get("hf_endpoint")
    return AutoRERuntimeConfig(
        base_modelscope_repo=str(
            raw.get("base_modelscope_repo", "AI-ModelScope/Mistral-7B-v0.1")
        ),
        adapter_repo=str(raw.get("adapter_repo", "dante123/AutoRE")),
        model_dir=str(raw.get("model_dir", "models/autore")),
        hf_endpoint=str(hf_endpoint).rstrip("/") if hf_endpoint else None,
        device=str(raw.get("device", "cuda")),
        load_in_4bit=bool(raw.get("load_in_4bit", True)),
        max_new_tokens=int(raw.get("max_new_tokens", 512)),
    )


def _model_root(config: AutoRERuntimeConfig) -> Path:
    path = Path(config.model_dir)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _base_model_dir(root: Path, config: AutoRERuntimeConfig) -> Path:
    safe_name = config.base_modelscope_repo.split("/")[-1].replace(":", "_")
    return root / "base" / safe_name


def _adapter_dir(root: Path, stage: Stage) -> Path:
    return root / _STAGE_DIR_NAMES[stage]


def _is_model_ready(path: Path) -> bool:
    return path.is_dir() and (path / "config.json").is_file()


def _adapter_expected_bytes(path: Path) -> int | None:
    weights = path / "adapter_model.safetensors"
    if not weights.is_file():
        return None
    try:
        import struct
        import json

        data = weights.read_bytes()
        if len(data) < 8:
            return None
        header_len = struct.unpack("<Q", data[:8])[0]
        header = json.loads(data[8 : 8 + header_len])
        max_end = max(
            value["data_offsets"][1]
            for value in header.values()
            if isinstance(value, dict) and "data_offsets" in value
        )
        return 8 + header_len + max_end
    except Exception:
        return None


def _is_adapter_ready(path: Path) -> bool:
    weights = path / "adapter_model.safetensors"
    if not weights.is_file() or not (path / "adapter_config.json").is_file():
        return False
    expected = _adapter_expected_bytes(path)
    if expected is None:
        return False
    actual = weights.stat().st_size
    if actual < expected:
        return False
    try:
        from safetensors import safe_open

        with safe_open(str(weights), framework="pt", device="cpu") as handle:
            next(iter(handle.keys()))
    except Exception:
        return False
    return True


def _adapter_integrity_error(path: Path) -> str | None:
    weights = path / "adapter_model.safetensors"
    if not weights.is_file():
        return f"{path.name}/ 缺少 adapter_model.safetensors（HF 仓库 fact 阶段可能未上传权重）"
    expected = _adapter_expected_bytes(path)
    actual = weights.stat().st_size
    if expected and actual < expected:
        return (
            f"{path.name}/adapter_model.safetensors 不完整："
            f"实际 {actual / 1e6:.1f}MB，期望约 {expected / 1e6:.0f}MB。"
            "hf-mirror 对 XET 大文件常只下到指针文件；需能访问 huggingface.co 并用 hf_xet 完整拉取，"
            "或从其他机器拷贝完整权重。"
        )
    try:
        from safetensors import safe_open

        with safe_open(str(weights), framework="pt", device="cpu") as handle:
            next(iter(handle.keys()))
    except Exception as exc:
        return f"{path.name}/adapter_model.safetensors 损坏：{exc}"
    return None


def _discover_adapter_path(root: Path, stage: Stage) -> Path | None:
    direct = _adapter_dir(root, stage)
    if _is_adapter_ready(direct):
        return direct
    # Legacy layouts from earlier downloads
    keywords = (_STAGE_DIR_NAMES[stage], "head" if stage == "head" else _STAGE_DIR_NAMES[stage])
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name == "base":
                continue
            name = child.name.lower()
            if any(key in name for key in keywords) and _is_adapter_ready(child):
                return child
    return None


def _missing_adapters(root: Path) -> list[str]:
    missing: list[str] = []
    for stage in ("relation", "head", "fact"):
        if not _discover_adapter_path(root, stage):
            missing.append(_STAGE_DIR_NAMES[stage])
    return missing


def _write_manifest(root: Path, config: AutoRERuntimeConfig) -> None:
    manifest = {
        "base_modelscope_repo": config.base_modelscope_repo,
        "adapter_repo": config.adapter_repo,
        "base_path": str(_base_model_dir(root, config)),
        "adapters": {
            stage: str(_discover_adapter_path(root, stage) or "")
            for stage in ("relation", "head", "fact")
        },
    }
    (root / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _download_hf_repo(
    repo_id: str,
    target: Path,
    *,
    allow_patterns: list[str] | None = None,
    hf_endpoint: str | None = None,
) -> Path:
    import os

    target.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "自动下载 AutoRE LoRA 需要 huggingface_hub: pip install huggingface_hub"
        ) from exc

    endpoint = hf_endpoint or os.environ.get("HF_ENDPOINT")
    if endpoint:
        endpoint = str(endpoint).rstrip("/")
        os.environ["HF_ENDPOINT"] = endpoint

    logger.info("[下载] %s -> %s (endpoint=%s)", repo_id, target, endpoint or "huggingface.co")
    print(f"[下载] 正在从 HuggingFace 下载 {repo_id} 到 {target} ...")
    kwargs: dict[str, Any] = {"local_dir": str(target)}
    if allow_patterns:
        kwargs["allow_patterns"] = allow_patterns
    if endpoint:
        kwargs["endpoint"] = endpoint
    snapshot_download(repo_id, **kwargs)
    print(f"[下载] 完成: {target}")
    return target


def _download_adapters(root: Path, config: AutoRERuntimeConfig) -> None:
    patterns = [f"{name}/*" for name in ("relation", "subject", "fact")]
    staging = root / ".download_adapters"
    if staging.exists():
        shutil.rmtree(staging)
    _download_hf_repo(
        config.adapter_repo,
        staging,
        allow_patterns=patterns,
        hf_endpoint=config.hf_endpoint,
    )
    for sub in ("relation", "subject", "fact"):
        src = staging / sub
        if not src.is_dir():
            continue
        dest = root / sub
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(src), str(dest))
    shutil.rmtree(staging, ignore_errors=True)
    problems = [
        err
        for stage in ("relation", "head", "fact")
        if (err := _adapter_integrity_error(_adapter_dir(root, stage)))
    ]
    if problems:
        raise RuntimeError("AutoRE LoRA 下载校验失败：\n- " + "\n- ".join(problems))


def _download_modelscope_repo(repo_id: str, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "自动下载 Mistral 基座需要 modelscope: pip install modelscope"
        ) from exc

    logger.info("[下载] %s -> %s (ModelScope)", repo_id, target)
    print(f"[下载] 正在从魔搭下载 {repo_id} 到 {target} ...")
    snapshot_download(repo_id, local_dir=str(target))
    print(f"[下载] 完成: {target}")
    return target


def _download_base(root: Path, config: AutoRERuntimeConfig) -> None:
    base_dir = _base_model_dir(root, config)
    _download_modelscope_repo(config.base_modelscope_repo, base_dir)


def ensure_autore_models(
    config: AutoRERuntimeConfig | None = None,
    *,
    allow_download: bool = True,
) -> Path:
    """Ensure models exist under model_dir; download base from ModelScope, adapters from HF."""
    cfg = config or config_from_yaml()
    root = _model_root(cfg)
    root.mkdir(parents=True, exist_ok=True)

    base_dir = _base_model_dir(root, cfg)
    missing_adapters = _missing_adapters(root)
    base_ready = _is_model_ready(base_dir)

    if not missing_adapters and base_ready:
        return root

    if not allow_download:
        missing: list[str] = []
        if not base_ready:
            missing.append(str(base_dir))
        missing.extend(missing_adapters)
        raise RuntimeError(
            "AutoRE 模型未就绪，缺少: " + ", ".join(missing) + "。"
            "首次跑 KG 会自动从魔搭下载 Mistral 基座、从 HuggingFace 下载 LoRA 适配器；"
            "国内可配置 kg.autore.hf_endpoint: https://hf-mirror.com。"
        )

    with _DOWNLOAD_LOCK:
        missing_adapters = _missing_adapters(root)
        base_dir = _base_model_dir(root, cfg)
        base_ready = _is_model_ready(base_dir)

        if missing_adapters:
            print(
                f"[下载] 首次 KG 抽取：LoRA 适配器不存在，从 HuggingFace 下载到 {root} ..."
            )
            _download_adapters(root, cfg)

        if not base_ready:
            print(
                f"[下载] 首次 KG 抽取：Mistral 基座不存在，从魔搭下载到 {base_dir} ..."
            )
            _download_base(root, cfg)

        if _missing_adapters(root):
            raise RuntimeError(
                f"AutoRE 适配器不完整: {root}，期望 relation/ subject/ fact/ 目录。"
            )
        if not _is_model_ready(base_dir):
            raise RuntimeError(f"AutoRE 基座模型下载校验失败: {base_dir}")

        _write_manifest(root, cfg)
        logger.info("AutoRE models ready under %s", root)
        return root


def model_status(config: AutoRERuntimeConfig | None = None) -> dict[str, Any]:
    cfg = config or config_from_yaml()
    root = _model_root(cfg)
    base_dir = _base_model_dir(root, cfg)
    missing_adapters = _missing_adapters(root)
    return {
        "root": str(root),
        "base_modelscope_repo": cfg.base_modelscope_repo,
        "adapter_repo": cfg.adapter_repo,
        "base_ready": _is_model_ready(base_dir),
        "base_path": str(base_dir),
        "adapters": {
            stage: str(_discover_adapter_path(root, stage) or "")
            for stage in ("relation", "head", "fact")
        },
        "adapters_ready": not missing_adapters,
        "missing_adapters": missing_adapters,
        "ready": _is_model_ready(base_dir) and not missing_adapters,
    }


def _load_base_model(config: AutoRERuntimeConfig, *, allow_download: bool = True) -> Any:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    global _TOKENIZER, _CONFIG_KEY
    root = ensure_autore_models(config, allow_download=allow_download)
    base_dir = _base_model_dir(root, config)
    cache_key = (str(base_dir), config.device, str(config.load_in_4bit))
    if _MODEL_CACHE.get("base") is not None and _CONFIG_KEY == cache_key:
        return _MODEL_CACHE["base"]

    use_cuda = config.device == "cuda" and torch.cuda.is_available()
    kwargs: dict[str, Any] = {}
    if use_cuda and config.load_in_4bit:
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = "auto"
    elif use_cuda:
        kwargs["device_map"] = "auto"
        kwargs["torch_dtype"] = torch.float16
    else:
        kwargs["torch_dtype"] = torch.float32
        kwargs["device_map"] = "cpu"
        logger.warning("CUDA unavailable; AutoRE running on CPU (very slow)")

    model = AutoModelForCausalLM.from_pretrained(str(base_dir), **kwargs)
    tokenizer = AutoTokenizer.from_pretrained(str(base_dir))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    _MODEL_CACHE["base"] = model
    _TOKENIZER = tokenizer
    _CONFIG_KEY = cache_key
    return model


def get_stage_model(
    config: AutoRERuntimeConfig,
    stage: Stage,
    *,
    allow_download: bool = True,
) -> tuple[Any, Any]:
    global _MODEL_CACHE
    with _AUTORE_LOCK:
        root = ensure_autore_models(config, allow_download=allow_download)
        adapter_path = _discover_adapter_path(root, stage)
        if adapter_path is None:
            raise RuntimeError(f"AutoRE adapter for stage '{stage}' not found in {root}")

        cache_name = f"stage:{stage}:{adapter_path}"
        if cache_name in _MODEL_CACHE and _TOKENIZER is not None:
            return _MODEL_CACHE[cache_name], _TOKENIZER

        from peft import PeftModel

        base = _load_base_model(config, allow_download=allow_download)
        model = PeftModel.from_pretrained(base, str(adapter_path))
        model.eval()
        _MODEL_CACHE[cache_name] = model
        return model, _TOKENIZER


def generate_text(
    config: AutoRERuntimeConfig,
    stage: Stage,
    prompt: str,
    *,
    allow_download: bool = True,
) -> str:
    import torch

    with _AUTORE_LOCK:
        model, tokenizer = get_stage_model(config, stage, allow_download=allow_download)
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=config.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        text = tokenizer.decode(output[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
        return text.strip()


def reset_autore_cache() -> None:
    global _MODEL_CACHE, _TOKENIZER, _CONFIG_KEY
    with _AUTORE_LOCK:
        _MODEL_CACHE = {}
        _TOKENIZER = None
        _CONFIG_KEY = None
