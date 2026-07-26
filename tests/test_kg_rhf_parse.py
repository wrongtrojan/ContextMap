import uuid

from services.kg.extract_rhf import _parse_lines, _parse_triples
from services.kg.types import TextChunk


def test_parse_lines_skips_no_relation():
    assert _parse_lines("no relation\n") == []
    assert _parse_lines("属于\n推导\n") == ["属于", "推导"]


def test_parse_triples_bracket_format():
    raw = "[欧拉方程, 属于, 常系数方程]"
    parsed = _parse_triples(raw, default_relation="属于", default_head="欧拉方程")
    assert parsed == [("欧拉方程", "属于", "常系数方程")]


def test_extract_triples_mock():
    from services.kg.extract_rhf import extract_triples_mock

    chunk = TextChunk(
        text="有符号数与无符号数之间存在转换关系。",
        source_unit_id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        modality="audio",
    )
    triples = extract_triples_mock(chunk)
    assert len(triples) == 1
    assert triples[0].relation == "相关"
