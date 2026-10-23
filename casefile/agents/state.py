"""Shared state for one investigation, and the trace every step writes.

Trace: runs/<case_id>/trace.jsonl, one JSON object per line:
  {ts, run_id, seq, step, agent, model, receipt_id, sql, input_summary, output}
`step` says what happened (plan, investigate, query, claims, review, fix, re_review,
verdict, memory_recall, memory_store, ...). The file is append-only; each investigation
has its own run_id, so several runs of one case can share the file.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from casefile.llm import RUNS_DIR


@dataclass
class CaseState:
    case_id: str
    mint: str
    symbol: str
    snapshot_tables: dict[str, str]          # short name -> casefile_snap.<table>
    source_urls: dict[str, str]              # short name -> API URL the data came from
    case_file: dict[str, Any]
    established: bool
    computed: dict[str, Any] = field(default_factory=dict)
    memories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # wallet -> recalled facts
    questions: list[dict[str, Any]] = field(default_factory=list)
    claims: dict[str, dict[str, Any]] = field(default_factory=dict)          # id -> claim
    decisions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # id -> reviews (in order)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    verdict: dict[str, Any] | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    llm_calls: int = 0
    models: set[str] = field(default_factory=set)
    started: float = field(default_factory=time.time)

    def accepted(self) -> list[dict[str, Any]]:
        return [c for cid, c in self.claims.items()
                if self.decisions.get(cid) and self.decisions[cid][-1]["decision"] == "accept"]


class Trace:
    """Append-only trace writer. on_event lets the CLI print each event as it happens."""

    def __init__(self, state: CaseState, on_event: Callable[[dict[str, Any]], None] | None = None):
        self.state = state
        self.path = RUNS_DIR / state.case_id / "trace.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.on_event = on_event
        self._lock = threading.Lock()
        self._seq = 0

    def log(self, step: str, agent: str, output: Any, *, model: str | None = None,
            receipt_id: str | None = None, sql: str | None = None, input_summary: str | None = None) -> dict:
        with self._lock:
            self._seq += 1
            event = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "run_id": self.state.run_id,
                "seq": self._seq,
                "case_id": self.state.case_id,
                "step": step,
                "agent": agent,
                "model": model,
                "receipt_id": receipt_id,
                "sql": sql,
                "input_summary": input_summary,
                "output": output,
            }
            with self.path.open("a") as f:
                f.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:  # printing must never break an investigation
                pass
        return event
