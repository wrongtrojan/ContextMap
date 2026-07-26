"""Tests for facet coverage."""

from services.evaluate.coverage import compute_coverage, extract_facets, facet_hits_in_text


def test_extract_facets_from_search_needs():
    facets = extract_facets(
        search_needs={"search_params": {"keywords": ["stack", "frame"], "semantic_query": "stack frame call"}},
        user_query="explain stack frame",
    )
    assert "stack" in [f.lower() for f in facets]


def test_compute_coverage_full():
    evidence = [{"content": "stack frame layout on the call stack"}]
    coverage, missing = compute_coverage(facets=["stack", "frame"], evidence=evidence)
    assert coverage == 1.0
    assert missing == []


def test_compute_coverage_partial():
    evidence = [{"content": "only stack mentioned"}]
    coverage, missing = compute_coverage(facets=["stack", "heap"], evidence=evidence)
    assert coverage == 0.5
    assert "heap" in missing


def test_facet_hits_case_insensitive():
    hits = facet_hits_in_text(["Stack"], "The STACK grows downward")
    assert hits == ["Stack"]
