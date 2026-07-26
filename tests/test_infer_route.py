"""Tests for infer routing."""

from services.evaluate.types import EvaluationReport, InferHints
from services.infer.route import route_infer


def test_route_visual_from_hints(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    image = frames / "frame.jpg"
    image.write_bytes(b"fake")

    evidence = [
        {
            "content_unit_id": "v1",
            "content": "diagram",
            "rerank_score": 0.8,
            "metadata": {
                "type": "frame",
                "has_visual_asset": True,
                "image_filename": image.name,
                "processed_path": str(tmp_path),
                "modality": "video",
            },
        }
    ]
    report = EvaluationReport(
        recommendation="proceed",
        confidence=0.9,
        evidence=evidence,
        scores=[],
        infer_hints=InferHints(visual_candidates=evidence),
    )
    trigger = route_infer(query="explain the diagram", evidence=evidence, eval_report=report)
    assert trigger.run_visual
    assert trigger.visual_requests
    assert trigger.visual_requests[0].image_path == str(image)
