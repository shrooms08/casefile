"""Normalized trace events for the UI (schema: docs/TRACE_SCHEMA.md).

The agents write raw events (casefile/agents/state.py). This adapter turns a run's raw events
into a stable list:

  {seq, ts, run_id, case_id, type, agent, model, receipt_id, title, detail}

Types: case_opened, memory_recalled, plan, investigator_started, sql_query, claim,
skeptic_decision, rework_requested, claim_dropped, retry, fallback, verdict, error.

normalize() is prefix-stable: the events produced for the first N raw lines never change
when more lines arrive, so a live stream can re-normalize and send only the new tail.
Run-level numbers (duration, LLM calls, memory stored) are returned by summarize().
"""

from __future__ import annotations

from typing import Any, Iterable

TYPES = ("case_opened", "memory_recalled", "plan", "investigator_started", "sql_query", "claim",
         "skeptic_decision", "rework_requested", "claim_dropped", "retry", "fallback", "verdict", "error")

_FAILED = {"investigator_failed", "fix_failed", "run_failed"}
_LLM_STEPS = {"plan", "investigate", "fix", "review", "re_review", "verdict"}
_FROM_LLM = {"claim", "skeptic_decision", "rework_requested", "verdict"}
_SKIP = {"investigate", "review", "re_review", "fix", "verdict", "memory_store", "done", "computed",
         "memory_observe"}


def _short(model: str | None) -> str | None:
    return model.split("/")[-1] if model else None


def _cut(s: Any, n: int = 110) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _evidence_line(e: dict) -> str:
    table = str(e.get("table") or "").split(".")[-1]
    return f"{table}.{e.get('field')}={e.get('value')}"


def normalize(raw: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    computed: dict | None = None
    observed: dict | None = None
    started: set[str] = set()
    native_started = False  # runs that record agent_version also log investigator_started themselves
    # Claims, decisions and the verdict are logged right after the LLM call that produced them;
    # that call's raw event carries the model and receipt, so carry them forward per agent.
    last_llm: dict[str, tuple] = {}

    def emit(r: dict, type_: str, title: str, detail: dict, agent: str | None = None) -> None:
        assert type_ in TYPES, type_
        model, receipt = r.get("model"), r.get("receipt_id")
        if not receipt and type_ in _FROM_LLM:
            model, receipt = last_llm.get(r.get("agent"), (model, receipt))
        out.append({
            "seq": len(out) + 1, "ts": r.get("ts"), "run_id": r.get("run_id"), "case_id": r.get("case_id"),
            "type": type_, "agent": agent or r.get("agent"), "model": model,
            "receipt_id": receipt, "title": title, "detail": detail,
        })

    for r in raw:
        step, agent, o = r.get("step"), r.get("agent"), r.get("output")
        if r.get("receipt_id") and step in _LLM_STEPS:
            last_llm[agent] = (r.get("model"), r.get("receipt_id"))
        if step == "computed":
            computed = o
        elif step == "memory_observe":
            observed = o
        if step in _SKIP:
            continue

        if step == "start":
            native_started = bool((o or {}).get("agent_version"))
            emit(r, "case_opened", f"Opened {o.get('symbol')} from {len(o.get('snapshot_tables') or {})} "
                                   f"frozen Zetaris snapshot tables",
                 {"mint": o.get("mint"), "symbol": o.get("symbol"), "snapshot_tables": o.get("snapshot_tables")})

        elif step == "memory_recall":
            facts = o.get("facts") or []
            custodians = [f for f in facts if f.get("kind") == "derived:custodian"]
            title = (f"H-MEM recalled {len(facts)} fact(s) for {o.get('wallets_with_memory', 0)} of "
                     f"{o.get('wallets_asked', 0)} wallets")
            if custodians:
                title += f"; {len(custodians)} likely custodian(s)"
            emit(r, "memory_recalled", title, {
                "wallets_asked": o.get("wallets_asked"), "wallets_with_memory": o.get("wallets_with_memory"),
                "facts": facts, "custodian_wallets": sorted({f["wallet"] for f in custodians}),
                "observed_this_case": observed, "seconds": o.get("seconds"),
            }, agent="h-mem")

        elif step == "plan":
            qs = o.get("questions") or []
            emit(r, "plan", f"Planner wrote {len(qs)} questions",
                 {"questions": qs, "computed": {k: v.get("value") for k, v in (computed or {}).items()}})
            # Older runs have no investigator_started event: the three start right after the plan.
            for a in (() if native_started else ("holders", "liquidity", "deployer")):
                mine = [q for q in qs if q.get("investigator") == a]
                if mine:
                    started.add(a)
                    emit({**r, "model": None, "receipt_id": None}, "investigator_started",
                         f"{a.capitalize()} investigator starts on {len(mine)} question(s)",
                         {"questions": mine, "synthesized": True}, agent=a)

        elif step == "investigator_started":
            if agent not in started:  # newer runs log it; skip if the plan already produced it
                started.add(agent)
                qs = (o or {}).get("questions") or []
                emit(r, "investigator_started", f"{str(agent).capitalize()} investigator starts on "
                                                f"{len(qs)} question(s)", {"questions": qs})

        elif step in ("query", "query_rejected", "query_error"):
            ok = step == "query"
            emit(r, "sql_query", (f"{agent} ran query_case: {o.get('rows')} rows" if ok
                                  else f"{agent} query refused: {_cut(o.get('error'), 80)}"),
                 {"sql": r.get("sql"), "ok": ok, "rows": o.get("rows") if ok else None,
                  "sample": o.get("sample") if ok else None, "error": None if ok else o.get("error")})

        elif step in ("claims", "revised_claims"):
            for c in o or []:
                ev = c.get("evidence") or []
                verified = sum(1 for e in ev if e.get("verified"))
                revised = "revision_of" in c
                emit(r, "claim", f"{c['id']}{' (revised)' if revised else ''}: {_cut(c.get('claim'))}", {
                    "id": c["id"], "claim": c.get("claim"), "confidence": c.get("confidence"),
                    "evidence": ev, "evidence_verified": f"{verified}/{len(ev)}",
                    "innocent_explanation_checked": c.get("innocent_explanation_checked"),
                    "revision_of": c.get("revision_of"),
                }, agent=c.get("agent") or agent)

        elif step == "decision":
            emit(r, "skeptic_decision", f"Skeptic {o['decision']}s {o['id']}: {_cut(o.get('reason'), 90)}",
                 {"id": o["id"], "decision": o["decision"], "reason": o.get("reason"),
                  "fix_request": o.get("fix_request"), "round": o.get("round")}, agent="skeptic")
            if o["decision"] == "reject" and o.get("round") == "review":
                emit(r, "rework_requested", f"{o['id']} sent back once: {_cut(o.get('fix_request'), 90)}",
                     {"id": o["id"], "fix_request": o.get("fix_request")}, agent="skeptic")

        elif step == "dropped":
            emit(r, "claim_dropped", f"{o['id']} dropped: {o.get('why')}",
                 {"id": o["id"], "why": o.get("why"), "claim": o.get("claim"), "reason": o.get("reason")})

        elif step.endswith("_fallback"):
            emit(r, "fallback", f"{agent}: deep model kept timing out, one try on the fast model",
                 {"step": step[: -len("_fallback")], **(o or {})})

        elif step.endswith("_error") or step.endswith("_invalid"):
            kind = "invalid output" if step.endswith("_invalid") else "call failed"
            emit(r, "retry", f"{agent} {step.rsplit('_', 1)[0]}: {kind}, retrying "
                             f"(attempt {(o or {}).get('attempt')})",
                 {"step": step.rsplit("_", 1)[0], "kind": kind, "attempt": (o or {}).get("attempt"),
                  "error": (o or {}).get("error") or "; ".join((o or {}).get("errors") or [])})

        elif step in _FAILED:
            emit(r, "error", f"{agent}: {_cut((o or {}).get('error'), 100)}",
                 {"step": step, "error": (o or {}).get("error")})

        elif step == "final":
            why = o.get("why") or []
            emit(r, "verdict", f"Verdict {o.get('label')}: {_cut(o.get('one_line'), 120)}",
                 {"label": o.get("label"), "one_line": o.get("one_line"), "why": why,
                  "what_would_change_my_mind": o.get("what_would_change_my_mind"),
                  "models_used": o.get("models_used")}, agent="verdict")
    return out


def summarize(raw: Iterable[dict]) -> dict[str, Any]:
    raw = list(raw)
    done = next((r["output"] for r in raw if r.get("step") == "done"), None)
    stored = next((r["output"] for r in raw if r.get("step") == "memory_store"), None)
    first, last = (raw[0]["ts"], raw[-1]["ts"]) if raw else (None, None)
    return {"run_id": raw[0]["run_id"] if raw else None, "started_at": first, "ended_at": last,
            "finished": done is not None, "stats": done, "memory_stored": stored}
