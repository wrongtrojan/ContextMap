"""Visual inference using Qwen2-VL in the main ContextMap environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from paths import PROJECT_ROOT
from services.common.modelscope_download import ensure_model_dir
from services.infer.config import load_infer_config


class VisualExpert:
    """Thin wrapper around vLLM for image captioning."""

    def __init__(self, model_dir: Path, *, device: str = "cuda") -> None:
        self.model_dir = model_dir
        self.device = device
        self._llm = None

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        try:
            from vllm import LLM, SamplingParams
        except ImportError as exc:
            raise RuntimeError(
                "vllm is required for visual inference. Install optional visual dependencies."
            ) from exc

        self._llm = LLM(
            model=str(self.model_dir),
            trust_remote_code=True,
            max_model_len=8192,
            limit_mm_per_prompt={"image": 4, "video": 1},
            gpu_memory_utilization=0.85,
            dtype="bfloat16",
        )
        self._sampling_params = SamplingParams(temperature=0.1, max_tokens=1024)

    def describe(self, *, query: str, image_path: str, evidence_text: str = "") -> str:
        self._ensure_loaded()
        from qwen_vl_utils import process_vision_info

        prompt = (
            f"User question: {query}\n"
            f"Evidence context: {evidence_text}\n"
            "Describe the image content relevant to the question."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        _text, images, _videos = process_vision_info(messages)
        outputs = self._llm.generate(
            {
                "prompt": prompt,
                "multi_modal_data": {"image": images[0] if images else None},
            },
            sampling_params=self._sampling_params,
        )
        if not outputs:
            return ""
        return outputs[0].outputs[0].text.strip()


@lru_cache(maxsize=1)
def _get_visual_expert() -> VisualExpert | None:
    cfg = load_infer_config()
    visual_cfg = cfg.get("visual") or {}
    if not visual_cfg.get("enabled", True):
        return None

    model_dir = PROJECT_ROOT / str(visual_cfg.get("model_dir", "models/qwen2-vl-7b-instruct"))
    modelscope_repo = str(visual_cfg.get("modelscope_repo", "qwen/Qwen2-VL-7B-Instruct"))
    ensure_model_dir(model_dir=model_dir, modelscope_repo=modelscope_repo)
    return VisualExpert(model_dir, device=str(visual_cfg.get("device", "cuda")))


def get_visual_expert() -> VisualExpert | None:
    return _get_visual_expert()
