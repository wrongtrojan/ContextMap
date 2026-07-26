"""Pydantic models for outline LLM output validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class OutlineSubPoint(BaseModel):
    heading: str
    summary: str
    anchor: float

    @field_validator("heading", "summary")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("heading and summary must be non-empty")
        return cleaned


class OutlineNode(BaseModel):
    heading: str
    summary: str
    anchor: float
    sub_points: list[OutlineSubPoint] = Field(default_factory=list)

    @field_validator("heading", "summary")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("heading and summary must be non-empty")
        return cleaned


class OutlineLLMResponse(BaseModel):
    title: str
    outline: list[OutlineNode]

    @field_validator("title")
    @classmethod
    def non_empty_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must be non-empty")
        return cleaned


def validate_outline_payload(
    payload: dict[str, Any],
    *,
    modality: str,
    max_anchor: float | None = None,
) -> tuple[OutlineLLMResponse, list[str]]:
    errors: list[str] = []
    try:
        parsed = OutlineLLMResponse.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        return OutlineLLMResponse(title="", outline=[]), [str(exc)]

    if not parsed.outline:
        errors.append("outline must contain at least one top-level node")

    for index, node in enumerate(parsed.outline):
        if node.anchor < 0:
            errors.append(f"outline[{index}].anchor must be >= 0")
        if max_anchor is not None and node.anchor > max_anchor:
            errors.append(f"outline[{index}].anchor exceeds max {max_anchor}")
        for sub_index, sub in enumerate(node.sub_points):
            if sub.anchor < 0:
                errors.append(f"outline[{index}].sub_points[{sub_index}].anchor must be >= 0")
            if max_anchor is not None and sub.anchor > max_anchor:
                errors.append(
                    f"outline[{index}].sub_points[{sub_index}].anchor exceeds max {max_anchor}"
                )

    if modality == "pdf":
        for index, node in enumerate(parsed.outline):
            if node.anchor < 1:
                errors.append(f"pdf outline[{index}].anchor should be >= 1 (page number)")
            for sub_index, sub in enumerate(node.sub_points):
                if sub.anchor < 1:
                    errors.append(
                        f"pdf outline[{index}].sub_points[{sub_index}].anchor should be >= 1"
                    )

    if errors:
        return parsed, errors
    return parsed, []
