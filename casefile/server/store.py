"""Where the API reads cases from: recorded runs (runs/<case_id>/<run_id>/, live mode) and
exported demo cases (demo_cases/<case_id>/, both modes). Pure file reads; no Zetaris, no LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from casefile.trace_schema import normalize, summarize

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = ROOT / "runs"
DEMO = ROOT / "demo_cases"


def _json(p: Path) -> Any:
    return json.loads(p.read_text()) if p.exists() else None


def _lines(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for l in p.read_text().splitlines():
        if l.strip():
            try:
                out.append(json.loads(l))
            except ValueError:  # a line still being written
                break
    return out


@dataclass
class Run:
    case_id: str
    run_id: str
    source: str                      # "runs" or "demo"
    path: Path
    events: list[dict] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    verdict: dict | None = None
    case_file: dict | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Store:
    def __init__(self, replay: bool, runs_dir: Path = RUNS, demo_dir: Path = DEMO):
        self.replay = replay
        self.runs_dir = runs_dir
        self.demo_dir = demo_dir

    # --- discovery ----------------------------------------------------------------------
    def demo_ids(self) -> list[str]:
        if not self.demo_dir.exists():
            return []
        return sorted(p.name for p in self.demo_dir.iterdir() if (p / "meta.json").exists())

    def run_ids(self, case_id: str) -> list[str]:
        d = self.runs_dir / case_id
        if self.replay or not d.is_dir():
            return []
        runs = [p for p in d.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "trace.jsonl").exists()]
        return [p.name for p in sorted(runs, key=lambda p: (_lines(p / "trace.jsonl")[:1] or [{"ts": ""}])[0]["ts"])]

    def case_ids(self) -> list[str]:
        ids = set(self.demo_ids())
        if not self.replay and self.runs_dir.exists():
            ids |= {p.name for p in self.runs_dir.iterdir() if p.name.startswith("m_") and self.run_ids(p.name)}
        return sorted(ids)

    # --- loading ------------------------------------------------------------------------
    def _demo_run(self, case_id: str) -> Run | None:
        d = self.demo_dir / case_id
        meta = _json(d / "meta.json")
        if not meta:
            return None
        return Run(case_id=case_id, run_id=meta["run_id"], source="demo", path=d,
                   events=_lines(d / "trace.jsonl"),
                   summary={"run_id": meta["run_id"], "finished": True,
                            "stats": {"seconds": meta.get("duration_s"), "llm_calls": meta.get("llm_calls"),
                                      "models": meta.get("models_used")},
                            "memory_stored": meta.get("memory_stored"), "started_at": meta.get("recorded_at")},
                   verdict=_json(d / "verdict.json"), case_file=_json(d / "case_file.json"),
                   meta={**meta, "source": "demo", "status": "done"})

    def _live_run(self, case_id: str, run_id: str, running: str | None = None) -> Run | None:
        d = self.runs_dir / case_id / run_id
        raw = _lines(d / "trace.jsonl")
        if not d.is_dir():
            return None
        verdict = _json(d / "verdict.json")
        cf = _json(d / "case_file.json")
        summ = summarize(raw)
        start = next((r["output"] for r in raw if r.get("step") == "start"), {}) or {}
        v = (verdict or {}).get("verdict") or {}
        failed = any(r.get("step") == "run_failed" for r in raw)
        status = "running" if running == run_id else "done" if verdict else "failed" if failed or raw else "starting"
        summary_row = ((cf or {}).get("case_file") or {}).get("summary") or {}
        meta = {
            "case_id": case_id, "run_id": run_id, "source": "runs", "status": status,
            "mint": start.get("mint") or (verdict or {}).get("mint"),
            "symbol": start.get("symbol") or (verdict or {}).get("symbol") or summary_row.get("symbol"),
            "rugcheck_rugged": summary_row.get("rugged"), "label": v.get("label"), "one_line": v.get("one_line"),
            "duration_s": (summ["stats"] or {}).get("seconds"), "llm_calls": (summ["stats"] or {}).get("llm_calls"),
            "models_used": v.get("models_used"), "recorded_at": summ["started_at"],
        }
        return Run(case_id=case_id, run_id=run_id, source="runs", path=d, events=normalize(raw),
                   summary=summ, verdict=verdict, case_file=cf, meta=meta)

    def run(self, case_id: str, run_id: str | None = None, running: str | None = None) -> Run | None:
        """A specific run, or the case's default: latest finished live run, else the demo run."""
        if run_id:
            if run_id in self.run_ids(case_id):
                return self._live_run(case_id, run_id, running)
            demo = self._demo_run(case_id)
            return demo if demo and demo.run_id == run_id else None
        ids = self.run_ids(case_id)
        for rid in reversed(ids):
            r = self._live_run(case_id, rid, running)
            if r and r.verdict:
                return r
        demo = self._demo_run(case_id)
        if demo:
            return demo
        return self._live_run(case_id, ids[-1], running) if ids else None

    def raw_path(self, case_id: str, run_id: str) -> Path:
        return self.runs_dir / case_id / run_id / "trace.jsonl"

    def memory(self) -> dict:
        if self.replay:
            return _json(self.demo_dir / "_memory.json") or {"items": [], "wallets": 0, "note": "no demo memory"}
        from casefile.memory_summary import summary
        return summary()


# --- shaping for the UI -------------------------------------------------------------------

def case_summary(cf_doc: dict | None) -> dict | None:
    if not cf_doc:
        return None
    cf, computed = cf_doc["case_file"], cf_doc.get("computed") or {}
    s, mint = cf.get("summary") or {}, cf.get("mint")
    own = [p for p in cf.get("pairs") or [] if p.get("base_address") == mint] or cf.get("pairs") or []
    best = max(own, key=lambda p: p.get("liquidity_usd") or 0) if own else None
    nets = cf.get("insider_networks") or []
    val = lambda k: (computed.get(k) or {}).get("value")
    return {
        "mint": mint, "symbol": s.get("symbol"), "name": s.get("name"),
        "rugcheck": {"score": s.get("score"), "score_normalised": s.get("score_normalised"), "rugged": s.get("rugged")},
        "best_pair": {k: best.get(k) for k in ("dex", "quote_symbol", "pair_address", "url", "liquidity_usd",
                                               "price_change_24h", "volume_24h", "fdv", "market_cap",
                                               "pair_created_at_ms")} if best else None,
        "pair_count": len(own),
        "holders": s.get("total_holders"),
        "top_holders": [{k: h.get(k) for k in ("owner", "pct", "insider", "label", "label_type")}
                        for h in (cf.get("top_holders") or [])[:10]],
        "risks": [{k: r.get(k) for k in ("name", "level", "value", "description")} for r in cf.get("risks") or []],
        "insider_networks": {"count": len(nets), "largest_size": max((n.get("size") or 0 for n in nets), default=0),
                             "accounts": sum(n.get("size") or 0 for n in nets),
                             "supply_pct": val("insider_networks_supply_pct"),
                             "largest_supply_pct": val("largest_insider_network_supply_pct"),
                             "graph_insiders_detected": s.get("graph_insiders_detected")},
        "creator": {"wallet": s.get("creator"), "balance": s.get("creator_balance")},
        "authorities": {k: s.get(k) for k in ("mint_authority", "freeze_authority", "update_authority",
                                              "metadata_mutable")},
        "established": cf_doc.get("established"),
        "computed": {k: v.get("value") for k, v in computed.items()},
        "sources": [{"kind": x.get("kind"), "zetaris_view": x.get("view"), "read_from": x.get("read_from"),
                     "via": x.get("via"), "api_url": x.get("api")} for x in cf.get("sources") or []],
        "captured_at": cf.get("captured_at"),
    }
