"""Tests for outline schema validation."""

from services.outline.schema import validate_outline_payload


def test_validate_pdf_outline_ok() -> None:
    payload = {
        "title": "AutoRE",
        "outline": [
            {
                "heading": "Introduction",
                "summary": "Overview of document-level RE.",
                "anchor": 1,
                "sub_points": [
                    {
                        "heading": "Motivation",
                        "summary": "Why DocRE matters.",
                        "anchor": 2,
                    }
                ],
            }
        ],
    }
    parsed, errors = validate_outline_payload(payload, modality="pdf", max_anchor=20)
    assert not errors
    assert parsed.title == "AutoRE"
    assert len(parsed.outline) == 1


def test_validate_rejects_empty_outline() -> None:
    payload = {"title": "Empty", "outline": []}
    _, errors = validate_outline_payload(payload, modality="pdf")
    assert errors


def test_validate_audio_outline_uses_seconds() -> None:
    payload = {
        "title": "CSAPP Clip",
        "outline": [
            {
                "heading": "Intro",
                "summary": "Opening remarks.",
                "anchor": 0.0,
                "sub_points": [
                    {
                        "heading": "Chapter 2",
                        "summary": "Information representation.",
                        "anchor": 10.7,
                    }
                ],
            }
        ],
    }
    parsed, errors = validate_outline_payload(payload, modality="audio", max_anchor=30.0)
    assert not errors
    assert parsed.outline[0].anchor == 0.0
