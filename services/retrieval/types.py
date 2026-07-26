"""Retrieval domain types."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from database.schemas import AssetRead, ContentUnitRead


class SearchPreferences(BaseModel):
    asset_name: str | None = None
    modality: str | None = None
    timestamp: float | None = None


class SearchParams(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    semantic_query: str | None = None
    top_k: int = 8


class RetrievalQuery(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    top_k: int = 8
    preferences: SearchPreferences = Field(default_factory=SearchPreferences)
    query_text: str = ""
    semantic_query: str = ""
    resolved_asset_id: uuid.UUID | None = None

    @classmethod
    def from_search_needs(cls, search_needs: dict[str, Any]) -> RetrievalQuery:
        params = search_needs.get("search_params") or {}
        prefs = search_needs.get("preferences") or {}
        keywords = [str(k).strip() for k in (params.get("keywords") or []) if str(k).strip()]
        top_k = int(params.get("top_k") or 8)
        query_text = " ".join(keywords)
        semantic = str(params.get("semantic_query") or "").strip()
        semantic_query = semantic or query_text
        return cls(
            keywords=keywords,
            top_k=max(1, top_k),
            query_text=query_text,
            semantic_query=semantic_query,
            preferences=SearchPreferences(
                asset_name=prefs.get("asset_name") or None,
                modality=prefs.get("modality") or None,
                timestamp=prefs.get("timestamp"),
            ),
        )


class ChannelHit(BaseModel):
    unit_id: uuid.UUID
    score: float
    channel: Literal["vector", "keyword", "graph"]
    rank: int
    unit: ContentUnitRead | None = None
    asset: AssetRead | None = None
    graph_entity: str | None = None
    graph_hop: int | None = None


class ScoredHit(BaseModel):
    unit_id: uuid.UUID
    unit: ContentUnitRead
    asset: AssetRead
    final_score: float
    rrf_score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    graph_score: float | None = None
    sources: list[str] = Field(default_factory=list)
    boosts: dict[str, float] = Field(default_factory=dict)


class HybridSearchDebug(BaseModel):
    channel_counts: dict[str, int] = Field(default_factory=dict)
    graph_skipped: bool = False
    graph_skip_reason: str | None = None
    graph_error: str | None = None
    dedup_removed: dict[str, int] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
