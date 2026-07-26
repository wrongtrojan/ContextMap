"""Evaluate module types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RefetchHint:
    top_k_multiplier: float = 1.5
    append_keywords: list[str] = field(default_factory=list)
    relax_modality: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_k_multiplier": self.top_k_multiplier,
            "append_keywords": list(self.append_keywords),
            "relax_modality": self.relax_modality,
        }


@dataclass
class EvidenceScore:
    content_unit_id: str
    rerank_score: float
    retrieval_score: float | None
    coverage_facets: list[str] = field(default_factory=list)
    decision_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_unit_id": self.content_unit_id,
            "rerank_score": round(self.rerank_score, 4),
            "retrieval_score": self.retrieval_score,
            "coverage_facets": list(self.coverage_facets),
            "decision_reason": self.decision_reason,
        }


@dataclass
class InferHints:
    need_sandbox: bool = False
    visual_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_sandbox": self.need_sandbox,
            "visual_candidates": self.visual_candidates,
        }


@dataclass
class EvaluationReport:
    recommendation: Literal["proceed", "refetch"]
    confidence: float
    evidence: list[dict[str, Any]]
    scores: list[EvidenceScore]
    missing_facets: list[str] = field(default_factory=list)
    refetch_hint: RefetchHint | None = None
    audit: dict[str, Any] | None = None
    infer_hints: InferHints = field(default_factory=InferHints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "scores": [score.to_dict() for score in self.scores],
            "missing_facets": list(self.missing_facets),
            "refetch_hint": self.refetch_hint.to_dict() if self.refetch_hint else None,
            "audit": self.audit,
            "infer_hints": self.infer_hints.to_dict(),
        }
