"""Human-readable progress reporting for live chat E2E runs."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field


_STEP_LABELS = {
    "prepare": "准备上下文",
    "research_search": "混合检索",
    "research_evaluate": "证据评估",
    "apply_refetch": "补充检索",
    "expand_media": "扩展媒体证据",
    "infer": "推理增强 (visual/sandbox)",
    "synthesize": "生成回答",
}

_STATUS_LABELS = {
    "idle": "空闲",
    "preparing": "准备中",
    "researching": "检索中",
    "evaluating": "评估中",
    "strengthening": "增强中",
    "finalizing": "生成中",
    "failed": "失败",
}


@dataclass
class LiveProgressTracker:
    """Aggregate SSE + poll events; print concise heartbeat lines."""

    label: str = "live"
    heartbeat_sec: float = 5.0
    started_at: float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)
    current_step: str | None = None
    current_status: str | None = None
    token_chars: int = 0
    token_events: int = 0
    refetch_count: int = 0
    infer_count: int = 0
    evaluation_count: int = 0
    evidence_count: int = 0
    last_event: str | None = None
    completed: bool = False
    error: str | None = None
    _seen_steps: list[str] = field(default_factory=list)

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def _log(self, message: str) -> None:
        print(f"[{self.label}] {self.elapsed():6.1f}s | {message}", flush=True)

    def maybe_heartbeat(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_heartbeat < self.heartbeat_sec:
            return
        self.last_heartbeat = now
        step = _STEP_LABELS.get(self.current_step or "", self.current_step or "-")
        status = _STATUS_LABELS.get(self.current_status or "", self.current_status or "-")
        self._log(
            f"heartbeat status={status} step={step} "
            f"tokens={self.token_events}({self.token_chars}ch) "
            f"refetch={self.refetch_count} infer={self.infer_count} "
            f"eval={self.evaluation_count} evidence={self.evidence_count} "
            f"last={self.last_event or '-'}"
        )

    def on_sse_payload(self, payload: dict) -> bool:
        """Record one SSE payload. Returns True when turn finished."""
        event_type = str(payload.get("type") or "message")
        self.last_event = event_type

        if event_type == "step_start":
            step = str(payload.get("step") or "")
            self.current_step = step or self.current_step
            self.current_status = str(payload.get("status") or self.current_status or "")
            if step and (not self._seen_steps or self._seen_steps[-1] != step):
                self._seen_steps.append(step)
            label = _STEP_LABELS.get(step, step or "unknown")
            status = _STATUS_LABELS.get(self.current_status, self.current_status or "-")
            self._log(f"step_start → {label} ({status})")
            self.maybe_heartbeat(force=True)
            return False

        if event_type == "state_change":
            self.current_status = str(payload.get("status") or self.current_status or "")
            self.maybe_heartbeat(force=True)
            return False

        if event_type == "evaluation":
            self.evaluation_count += 1
            recommendation = payload.get("recommendation")
            confidence = payload.get("confidence")
            self._log(f"evaluation #{self.evaluation_count} rec={recommendation} conf={confidence}")
            return False

        if event_type == "refetch":
            self.refetch_count += 1
            hint = payload.get("refetch_hint") or {}
            reason = hint.get("reason") or hint.get("query_hint") or "n/a"
            self._log(f"refetch #{self.refetch_count} reason={str(reason)[:80]}")
            return False

        if event_type == "evidence_snapshot":
            self.evidence_count = int(payload.get("count") or self.evidence_count)
            self._log(f"evidence_snapshot count={self.evidence_count}")
            return False

        if event_type == "infer_result":
            self.infer_count += 1
            kind = payload.get("kind") or "unknown"
            summary = str(payload.get("summary") or "")[:120]
            self._log(f"infer_result #{self.infer_count} kind={kind} summary={summary!r}")
            return False

        if event_type == "token":
            content = str(payload.get("content") or "")
            self.token_events += 1
            self.token_chars += len(content)
            if self.token_events == 1:
                self._log("synthesize streaming started")
            elif self.token_events % 50 == 0:
                self._log(f"synthesize streaming… tokens={self.token_events} chars={self.token_chars}")
            self.maybe_heartbeat()
            return False

        if event_type == "completed":
            self.completed = True
            self._log("completed")
            self.print_summary()
            return True

        if event_type == "error":
            self.error = str(payload.get("message") or payload)
            self._log(f"ERROR {self.error}")
            self.print_summary()
            return True

        if event_type not in {"ping", "None", ""}:
            self._log(f"event {event_type}")
        self.maybe_heartbeat()
        return False

    def on_poll_detail(self, detail: dict) -> None:
        self.current_status = str(detail.get("status") or self.current_status or "")
        self.current_step = str(detail.get("current_step") or self.current_step or "") or self.current_step
        self.evidence_count = max(self.evidence_count, len(detail.get("evidences") or []))

    def print_summary(self) -> None:
        steps = " → ".join(_STEP_LABELS.get(s, s) for s in self._seen_steps) or "-"
        self._log(
            f"summary elapsed={self.elapsed():.1f}s steps=[{steps}] "
            f"tokens={self.token_events} refetch={self.refetch_count} "
            f"infer={self.infer_count} eval={self.evaluation_count} "
            f"evidence={self.evidence_count} completed={self.completed} error={self.error}"
        )


def parse_sse_lines(line: str, *, data_buffer: list[str]) -> dict | None:
    """Parse one SSE line; return payload when data block completes."""
    if line.startswith("data:"):
        data_buffer.append(line.removeprefix("data:").strip())
        return None
    if line == "" and data_buffer:
        raw = "\n".join(data_buffer)
        data_buffer.clear()
        if not raw:
            return None
        return json.loads(raw)
    return None
