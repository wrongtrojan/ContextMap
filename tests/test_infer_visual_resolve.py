"""Tests for visual media path resolution."""

from services.infer.visual.resolve_media import resolve_image_path


def test_resolve_frame_from_processed_path(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    image = frames_dir / "time_1.00.jpg"
    image.write_bytes(b"x")

    evidence = {
        "metadata": {
            "type": "frame",
            "modality": "video",
            "image_filename": "time_1.00.jpg",
            "processed_path": str(tmp_path),
            "has_visual_asset": True,
        }
    }
    resolved = resolve_image_path(evidence)
    assert resolved == image
