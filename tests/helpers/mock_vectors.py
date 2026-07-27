"""Deterministic fake embedding vectors for unit/integration tests."""

from __future__ import annotations

import math


def fake_vector(seed: float, *, dim: int = 1024) -> list[float]:
    values = [math.sin(seed * (index + 1)) for index in range(dim)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def mock_embed_texts(texts: list[str]) -> list[list[float]]:
    return [fake_vector(float(index + 1)) for index in range(len(texts))]
