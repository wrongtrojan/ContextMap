"""Format scored hits as legacy-compatible evidence dicts."""

from __future__ import annotations

from services.retrieval.resolve import display_content, page_label, timestamp_seconds
from services.retrieval.types import ScoredHit


def format_evidence(hit: ScoredHit, *, rank: int) -> dict:
    modality = hit.asset.modality.value
    unit = hit.unit
    meta = unit.metadata or {}
    image_filename = meta.get("image_filename")
    minio_key = meta.get("minio_key")
    return {
        "content_unit_id": str(hit.unit_id),
        "score": round(hit.final_score, 4),
        "base_vector_score": round(hit.vector_score, 4) if hit.vector_score is not None else None,
        "keyword_score": round(hit.keyword_score, 4) if hit.keyword_score is not None else None,
        "graph_score": round(hit.graph_score, 4) if hit.graph_score is not None else None,
        "content": display_content(unit),
        "metadata": {
            "asset_id": str(hit.asset.id),
            "asset_name": hit.asset.name,
            "modality": modality,
            "type": unit.content_type.value,
            "timestamp": timestamp_seconds(unit, modality),
            "page_label": page_label(unit, modality),
            "sources": hit.sources,
            "rank": rank,
            "rrf_score": round(hit.rrf_score, 4),
            "boosts": hit.boosts,
            "image_filename": image_filename,
            "minio_key": minio_key,
            "minio_bucket": meta.get("minio_bucket"),
            "has_visual_asset": bool(image_filename or minio_key),
            "context_source": meta.get("context_source"),
            "processed_path": hit.asset.processed_path,
        },
    }


def format_results(hits: list[ScoredHit]) -> list[dict]:
    return [format_evidence(hit, rank=index) for index, hit in enumerate(hits)]
