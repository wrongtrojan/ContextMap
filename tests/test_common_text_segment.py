"""Unit tests for text segmentation."""

from services.common.text_segment import (
    expand_query_tokens,
    has_cjk,
    segment_for_fts,
    segment_tokens,
)


def test_has_cjk():
    assert has_cjk("虚拟内存")
    assert not has_cjk("virtual memory")


def test_segment_chinese():
    tokens = segment_tokens("虚拟内存的页表结构")
    assert "虚拟内存" in tokens
    assert "页表" in tokens


def test_segment_english_passthrough():
    tokens = segment_tokens("virtual memory page table")
    assert "virtual" in tokens
    assert "memory" in tokens
    assert "page" in tokens


def test_segment_for_fts_empty():
    assert segment_for_fts("") == ""
    assert segment_for_fts("   ") == ""


def test_expand_query_tokens_deduplicates():
    tokens = expand_query_tokens("虚拟内存 页表", "虚拟内存")
    assert tokens.count("虚拟内存") == 1
    assert "页表" in tokens
