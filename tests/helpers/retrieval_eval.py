"""Shared retrieval evaluation utilities (recall + precision)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from sqlalchemy import func, select

from database.enums import AssetStatus, ContentType
from database.models import Asset, ContentUnit
from database.session import get_session
from services.common.text_segment import has_cjk, segment_tokens
from services.retrieval.search import hybrid_search

MIN_READY_ASSETS = 3
MIN_TEXT_UNITS = 50
IN_CORPUS_CASES = 30
IN_CORPUS_SEED = 42
DEFAULT_TOP_K = 5

# (query text, relevance needle, optional modality filter)
NL_EVAL_CASES: list[tuple[str, str, str | None]] = [
    ("document-level relation extraction", "AutoRE", "pdf"),
    ("QLoRA fine-tuning relation extraction", "QLoRA", "pdf"),
    ("large language model relation extraction", "relation", "pdf"),
    ("ChatGPT relation extraction paradigm", "ChatGPT", "pdf"),
    ("RHF step-by-step triplet extraction", "RHF", "pdf"),
    ("AutoRE document level RE", "AutoRE", "pdf"),
    ("head entity relation tail extraction", "head", "pdf"),
    ("Mistral fine-tuning document RE", "Mistral", "pdf"),
    ("precision recall F1 relation extraction", "Precision", "pdf"),
    ("open domain relation extraction", "open", "pdf"),
    ("virtual memory page table", "page", None),
    ("cache memory hierarchy", "cache", None),
    ("process scheduling operating system", "process", None),
    ("stack frame function call", "stack", None),
    ("pointer dereference memory", "pointer", None),
    ("file descriptor unix", "file", None),
    ("thread synchronization mutex", "thread", None),
    ("instruction pipeline CPU", "pipeline", None),
    ("heap memory allocation", "heap", None),
    ("system call kernel", "system", None),
    ("linker relocation symbol", "link", None),
    ("buffer overflow security", "buffer", None),
    ("fork exec shell", "fork", None),
    ("signal handler interrupt", "signal", None),
    ("dynamic memory malloc free", "malloc", None),
    ("虚拟内存 页表", "虚拟", None),
    ("缓存 局部性", "缓存", None),
    ("进程 调度", "进程", None),
    ("栈 帧 函数", "栈", None),
    ("指针 解引用", "指针", None),
]


@dataclass
class QueryMetrics:
    recall: float = 0.0
    precision: float = 0.0
    reciprocal_rank: float = 0.0

    @property
    def f1(self) -> float:
        if self.recall + self.precision == 0:
            return 0.0
        return 2 * self.recall * self.precision / (self.recall + self.precision)


@dataclass
class EvalReport:
    top_k: int
    queries: int = 0
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    f1_at_k: float = 0.0
    mrr: float = 0.0
    per_query: list[QueryMetrics] = field(default_factory=list)

    @classmethod
    def from_query_metrics(cls, metrics: list[QueryMetrics], *, top_k: int) -> EvalReport:
        if not metrics:
            return cls(top_k=top_k, queries=0)
        n = len(metrics)
        recall = sum(item.recall for item in metrics) / n
        precision = sum(item.precision for item in metrics) / n
        f1 = sum(item.f1 for item in metrics) / n
        mrr = sum(item.reciprocal_rank for item in metrics) / n
        return cls(
            top_k=top_k,
            queries=n,
            recall_at_k=recall,
            precision_at_k=precision,
            f1_at_k=f1,
            mrr=mrr,
            per_query=metrics,
        )


@dataclass
class ModeComparison:
    mode: str
    in_corpus: EvalReport
    nl_queries: EvalReport

    @property
    def combined(self) -> EvalReport:
        all_metrics = self.in_corpus.per_query + self.nl_queries.per_query
        return EvalReport.from_query_metrics(all_metrics, top_k=self.in_corpus.top_k)


async def corpus_available() -> tuple[bool, str]:
    async with get_session() as session:
        ready = await session.scalar(
            select(func.count()).select_from(Asset).where(Asset.status == AssetStatus.READY)
        )
        text_units = await session.scalar(
            select(func.count())
            .select_from(ContentUnit)
            .join(Asset)
            .where(
                Asset.status == AssetStatus.READY,
                ContentUnit.content_type.in_([ContentType.TEXT, ContentType.TRANSCRIPT]),
                func.length(ContentUnit.search_text) > 50,
            )
        )
    if (ready or 0) < MIN_READY_ASSETS:
        return False, f"need >= {MIN_READY_ASSETS} READY assets, got {ready}"
    if (text_units or 0) < MIN_TEXT_UNITS:
        return False, f"need >= {MIN_TEXT_UNITS} text/transcript units, got {text_units}"
    return True, ""


def keyword_only_config(cfg: dict) -> dict:
    return {
        **cfg,
        "channels": {
            **cfg["channels"],
            "vector": {**cfg["channels"]["vector"], "enabled": False},
            "graph": {**cfg["channels"]["graph"], "enabled": False},
        },
    }


def vector_only_config(cfg: dict) -> dict:
    return {
        **cfg,
        "channels": {
            **cfg["channels"],
            "keyword": {**cfg["channels"]["keyword"], "enabled": False},
            "graph": {**cfg["channels"]["graph"], "enabled": False},
        },
    }


def extract_keywords(text: str) -> list[str]:
    if has_cjk(text):
        return segment_tokens(text)[:3]
    words = [
        w.strip('.,;:()[]"\'')
        for w in re.split(r"\s+", text.replace("\n", " "))
        if len(w.strip('.,;:()[]"\'')) >= 4
    ]
    return words[:3]


def extract_nl_keywords(query: str) -> list[str]:
    if has_cjk(query):
        return segment_tokens(query)[:3]
    words = [w.strip('.,;:()[]"\'') for w in query.split() if w.strip('.,;:()[]"\'')]
    if len(words) >= 2:
        return words[:3]
    return words


async def run_search(search_needs: dict, config: dict, *, top_k: int) -> list[dict]:
    async with get_session() as session:
        response = await hybrid_search(session, search_needs=search_needs, config=config)
    if response["status"] != "success":
        raise RuntimeError(response.get("message", "hybrid_search failed"))
    return response.get("results", [])[:top_k]


def _metrics_single_target(results: list[dict], target_unit_id: str, *, top_k: int) -> QueryMetrics:
    relevant_ranks = [
        rank
        for rank, item in enumerate(results[:top_k], start=1)
        if item["content_unit_id"] == target_unit_id
    ]
    relevant_count = len(relevant_ranks)
    return QueryMetrics(
        recall=1.0 if relevant_count else 0.0,
        precision=relevant_count / top_k,
        reciprocal_rank=1.0 / relevant_ranks[0] if relevant_ranks else 0.0,
    )


def _metrics_needle(results: list[dict], needle: str, *, top_k: int) -> QueryMetrics:
    needle_lower = needle.lower()
    relevant_ranks = [
        rank
        for rank, item in enumerate(results[:top_k], start=1)
        if needle_lower in item["content"].lower()
    ]
    relevant_count = len(relevant_ranks)
    return QueryMetrics(
        recall=1.0 if relevant_count else 0.0,
        precision=relevant_count / top_k,
        reciprocal_rank=1.0 / relevant_ranks[0] if relevant_ranks else 0.0,
    )


async def _load_in_corpus_cases(limit: int = IN_CORPUS_CASES) -> list[tuple[str, str]]:
    async with get_session() as session:
        rows = (
            await session.execute(
                select(ContentUnit.id, ContentUnit.search_text)
                .join(Asset)
                .where(
                    Asset.status == AssetStatus.READY,
                    ContentUnit.content_type.in_([ContentType.TEXT, ContentType.TRANSCRIPT]),
                    func.length(ContentUnit.search_text) > 50,
                )
                .order_by(ContentUnit.id)
            )
        ).all()

    rng = random.Random(IN_CORPUS_SEED)
    pool = list(rows)
    rng.shuffle(pool)

    cases: list[tuple[str, str]] = []
    for unit_id, text in pool:
        if len(cases) >= limit:
            break
        keywords = extract_keywords(text)
        if len(keywords) < 2:
            continue
        cases.append((str(unit_id), " ".join(keywords)))
    return cases


async def eval_in_corpus(config: dict, *, top_k: int = DEFAULT_TOP_K) -> EvalReport:
    metrics: list[QueryMetrics] = []
    for unit_id, keyword_text in await _load_in_corpus_cases():
        keywords = keyword_text.split()
        search_needs = {"search_params": {"keywords": keywords, "top_k": top_k}, "preferences": {}}
        results = await run_search(search_needs, config, top_k=top_k)
        metrics.append(_metrics_single_target(results, unit_id, top_k=top_k))
    return EvalReport.from_query_metrics(metrics, top_k=top_k)


async def eval_nl_queries(
    config: dict,
    *,
    top_k: int = DEFAULT_TOP_K,
    cases: list[tuple[str, str, str | None]] | None = None,
) -> EvalReport:
    metrics: list[QueryMetrics] = []
    for query, needle, modality in cases or NL_EVAL_CASES:
        prefs = {"modality": modality} if modality else {}
        search_needs = {
            "search_params": {
                "keywords": extract_nl_keywords(query),
                "semantic_query": query,
                "top_k": top_k,
            },
            "preferences": prefs,
        }
        results = await run_search(search_needs, config, top_k=top_k)
        metrics.append(_metrics_needle(results, needle, top_k=top_k))
    return EvalReport.from_query_metrics(metrics, top_k=top_k)


async def eval_mode(config: dict, *, mode: str, top_k: int = DEFAULT_TOP_K) -> ModeComparison:
    in_corpus = await eval_in_corpus(config, top_k=top_k)
    nl_queries = await eval_nl_queries(config, top_k=top_k)
    return ModeComparison(mode=mode, in_corpus=in_corpus, nl_queries=nl_queries)


async def eval_all_modes(
    base_config: dict,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[ModeComparison]:
    configs = {
        "hybrid": base_config,
        "keyword_only": keyword_only_config(base_config),
        "vector_only": vector_only_config(base_config),
    }
    reports: list[ModeComparison] = []
    for mode, config in configs.items():
        reports.append(await eval_mode(config, mode=mode, top_k=top_k))
    return reports


def format_report(report: EvalReport) -> str:
    return (
        f"R@{report.top_k}={report.recall_at_k:.0%} "
        f"P@{report.top_k}={report.precision_at_k:.0%} "
        f"F1={report.f1_at_k:.0%} MRR={report.mrr:.3f} (n={report.queries})"
    )
