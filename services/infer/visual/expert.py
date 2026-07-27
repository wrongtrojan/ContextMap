"""Visual inference using Qwen2-VL in the main ContextMap environment."""

from __future__ import annotations

import concurrent.futures
from functools import lru_cache
from pathlib import Path
from typing import Any

from paths import PROJECT_ROOT
from services.common.modelscope_download import ensure_model_dir
from services.infer.config import load_infer_config
from services.infer.preflight import check_visual_runtime


class VisualExpert:
    """Thin wrapper around vLLM for image captioning."""

    def __init__(self, model_dir: Path, *, device: str = "cuda", config: dict[str, Any]) -> None:
        self.model_dir = model_dir
        self.device = device
        self._config = config
        self._llm = None
        self._processor = None
        self._sampling_params = None
        self._load_error: str | None = None

    def _visual_cfg(self) -> dict[str, Any]:
        return dict(self._config.get("visual") or {})

    def _load_timeout_sec(self) -> float:
        return float(self._visual_cfg().get("timeout_sec", 120))

    def _ensure_loaded(self) -> None:
        if self._load_error is not None:
            raise RuntimeError(self._load_error)
        if self._llm is not None:
            return

        preflight_error = check_visual_runtime(self._config)
        if preflight_error is not None:
            self._load_error = preflight_error
            raise RuntimeError(preflight_error)

        visual_cfg = self._visual_cfg()
        enforce_eager = bool(visual_cfg.get("enforce_eager", True))
        timeout = self._load_timeout_sec()

        def _load() -> None:
            from vllm import LLM, SamplingParams

            self._llm = LLM(
                model=str(self.model_dir),
                trust_remote_code=True,
                max_model_len=int(visual_cfg.get("max_model_len", 8192)),
                limit_mm_per_prompt={"image": 4, "video": 1},
                gpu_memory_utilization=float(visual_cfg.get("gpu_memory_utilization", 0.85)),
                dtype=str(visual_cfg.get("dtype", "bfloat16")),
                enforce_eager=enforce_eager,
            )
            self._sampling_params = SamplingParams(
                temperature=float(visual_cfg.get("temperature", 0.1)),
                max_tokens=int(visual_cfg.get("max_tokens", 1024)),
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_load)
                future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            self._load_error = f"visual model load exceeded {timeout:.0f}s"
            raise TimeoutError(self._load_error) from exc
        except Exception as exc:
            self._load_error = str(exc)
            raise

    def _describe_impl(self, *, query: str, image_path: str, evidence_text: str) -> str:
        from qwen_vl_utils import process_vision_info
        from transformers import AutoProcessor

        if self._processor is None:
            self._processor = AutoProcessor.from_pretrained(
                str(self.model_dir),
                trust_remote_code=True,
            )

        prompt_text = (
            f"User question: {query}\n"
            f"Evidence context: {evidence_text}\n"
            "Describe the image content relevant to the question."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        prompt = self._processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = process_vision_info(messages)
        mm_data: dict[str, Any] = {}
        if image_inputs is not None:
            mm_data["image"] = image_inputs
        if video_inputs is not None:
            mm_data["video"] = video_inputs

        outputs = self._llm.generate(
            [{"prompt": prompt, "multi_modal_data": mm_data}],
            sampling_params=self._sampling_params,
        )
        if not outputs:
            return ""
        return outputs[0].outputs[0].text.strip()

    def describe(self, *, query: str, image_path: str, evidence_text: str = "") -> str:
        self._ensure_loaded()
        timeout = self._load_timeout_sec()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._describe_impl,
                    query=query,
                    image_path=image_path,
                    evidence_text=evidence_text,
                )
                return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(f"visual inference exceeded {timeout:.0f}s") from exc


@lru_cache(maxsize=1)
def _get_visual_expert() -> VisualExpert | None:
    cfg = load_infer_config()
    visual_cfg = cfg.get("visual") or {}
    if not visual_cfg.get("enabled", True):
        return None

    model_dir = PROJECT_ROOT / str(visual_cfg.get("model_dir", "models/qwen2-vl-7b-instruct"))
    modelscope_repo = str(visual_cfg.get("modelscope_repo", "qwen/Qwen2-VL-7B-Instruct"))
    ensure_model_dir(model_dir=model_dir, modelscope_repo=modelscope_repo)
    return VisualExpert(
        model_dir,
        device=str(visual_cfg.get("device", "cuda")),
        config=cfg,
    )


def get_visual_expert() -> VisualExpert | None:
    return _get_visual_expert()


def reset_visual_expert_cache() -> None:
    _get_visual_expert.cache_clear()
