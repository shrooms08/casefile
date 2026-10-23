"""The investigation loop (plain Python, no framework).

  open case (reuse snapshots) -> recall H-MEM for creator + top-20 holders
  -> Planner (deep) -> 3 Investigators (fast, concurrent; Zetaris calls stay serialized)
  -> Skeptic (deep) -> one fix round for rejected claims -> Skeptic re-review
  -> Verdict (deep, accepted claims only) -> store H-MEM memories

Every step lands in runs/<case_id>/trace.jsonl.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from casefile import memory
from casefile.agents import prompts
from casefile.agents.evidence import computed_fields, expand_evidence, slices, table_columns
from casefile.agents.llmjson import StepFailed, call_json
from casefile.agents.state import CaseState, Trace, run_dir
from casefile.agents.tools import query_case
from casefile.case_file import get_case_file
from casefile.sources import _load_registry

INVESTIGATORS = ("holders", "liquidity", "deployer")
PREFIX = {"holders": "H", "liquidity": "L", "deployer": "D"}
LABELS = ("RUGGED", "HIGH_RISK", "CAUTION", "NO_RUG_EVIDENCE")
CONF = ("low", "medium", "high")
EVIDENCE_TABLES = {"summary", "holders", "pairs", "markets", "risks", "insiders", "lockers", "computed", "H-MEM"}
MAX_QUERIES = 2


def _dumps(x: Any) -> str:
    return json.dumps(x, default=str, ensure_ascii=False, separators=(",", ":"))


# --- validators -------------------------------------------------------------------------

def _v_plan(d: Any) -> list[str]:
    qs = d.get("questions") if isinstance(d, dict) else None
    if not isinstance(qs, list) or not 3 <= len(qs) <= 5:
        return ["questions must be a list of 3-5 items"]
    errs = [f"question {i}: investigator must be one of {INVESTIGATORS}" for i, q in enumerate(qs)
            if not isinstance(q, dict) or q.get("investigator") not in INVESTIGATORS or not q.get("question")]
    missing = set(INVESTIGATORS) - {q.get("investigator") for q in qs if isinstance(q, dict)}
    if missing:
        errs.append(f"every investigator needs a question; missing {sorted(missing)}")
    return errs


def _v_claim(c: Any, i: int) -> list[str]:
    if not isinstance(c, dict):
        return [f"claim {i} is not an object"]
    errs = []
    if not c.get("id") or not isinstance(c.get("claim"), str) or not c["claim"].strip():
        errs.append(f"claim {i}: needs id and claim sentence")
    ev = c.get("evidence")
    if not isinstance(ev, list) or not ev:
        errs.append(f"claim {i}: evidence must be a non-empty list")
    else:
        for e in ev:
            if not isinstance(e, dict) or e.get("table") not in EVIDENCE_TABLES or "field" not in e or "value" not in e:
                errs.append(f"claim {i}: each evidence item needs table (one of {sorted(EVIDENCE_TABLES)}), field, value")
                break
    if c.get("confidence") not in CONF:
        errs.append(f"claim {i}: confidence must be low|medium|high")
    if not c.get("innocent_explanation_checked"):
        errs.append(f"claim {i}: innocent_explanation_checked is required")
    return errs


def _normalise_action(d: Any) -> Any:
    """Models often drop the "action" key: claims means final, sql means query."""
    if isinstance(d, dict) and d.get("action") not in ("query", "final"):
        if d.get("claims"):
            d["action"] = "final"
        elif d.get("sql"):
            d["action"] = "query"
    return d


def _v_investigator(d: Any) -> list[str]:
    d = _normalise_action(d)
    if not isinstance(d, dict) or d.get("action") not in ("query", "final"):
        return ['reply must have action "query" or "final"']
    if d["action"] == "query":
        return [] if isinstance(d.get("sql"), str) and d["sql"].strip() else ["query needs sql"]
    claims = d.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["final needs a non-empty claims list"]
    return [e for i, c in enumerate(claims) for e in _v_claim(c, i)]


def _v_fix(d: Any) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("claims", []), list):
        return ["reply must be {claims: [...], withdrawn: [...]}"]
    return [e for i, c in enumerate(d.get("claims", [])) for e in _v_claim(c, i)]


def _v_reviews(ids: set[str]) -> Callable[[Any], list[str]]:
    def v(d: Any) -> list[str]:
        rs = d.get("reviews") if isinstance(d, dict) else None
        if not isinstance(rs, list):
            return ["reviews must be a list"]
        errs = [f"review {r.get('id') if isinstance(r, dict) else i}: decision must be accept or reject"
                for i, r in enumerate(rs) if not isinstance(r, dict) or r.get("decision") not in ("accept", "reject")]
        got = {r.get("id") for r in rs if isinstance(r, dict)}
        if ids - got:
            errs.append(f"missing reviews for {sorted(ids - got)}")
        return errs
    return v


def _v_verdict(accepted: set[str]) -> Callable[[Any], list[str]]:
    def v(d: Any) -> list[str]:
        if not isinstance(d, dict):
            return ["verdict must be an object"]
        errs = []
        if d.get("label") not in LABELS:
            errs.append(f"label must be one of {LABELS}")
        if not d.get("one_line"):
            errs.append("one_line is required")
        why = d.get("why")
        if not isinstance(why, list) or (accepted and not why):
            errs.append("why must be a non-empty list")
        else:
            for w in why:
                if not isinstance(w, dict) or w.get("claim_id") not in accepted or not w.get("sentence"):
                    errs.append(f"why item {w!r:.80} must cite an ACCEPTED claim_id ({sorted(accepted)}) with a sentence")
        if not d.get("what_would_change_my_mind"):
            errs.append("what_would_change_my_mind is required")
        return errs
    return v


# --- setup ------------------------------------------------------------------------------

def _build_state(mint: str) -> CaseState:
    cf = get_case_file(mint)
    if cf["mode"] != "snapshot":
        raise RuntimeError(f"case file for {mint} is not on snapshots: {cf['errors']}")
    reg = _load_registry()[cf["mint"]]
    snaps = reg["snapshots"]
    tables = {"summary": "summary", "pairs": "pairs", "markets": "markets", "risks": "risks",
              "insiders": "insiders", "lockers": "lockers",
              "holders": "holders_labelled" if "holders_labelled" in snaps else "holders"}
    snapshot_tables = {short: snaps[key]["table"] for short, key in tables.items() if key in snaps}
    return CaseState(case_id=cf["case_id"], mint=cf["mint"], symbol=cf["summary"].get("symbol") or "?",
                     snapshot_tables=snapshot_tables, source_urls=reg["urls"], case_file=cf, established=False)


def _claim_ids_unique(state: CaseState, agent: str, claims: list[dict]) -> list[dict]:
    out = []
    for i, c in enumerate(claims, 1):
        cid = str(c.get("id") or f"{PREFIX[agent]}{i}")
        if not cid.startswith(PREFIX[agent]):
            cid = f"{PREFIX[agent]}{i}"
        while cid in state.claims and state.claims[cid]["agent"] != agent:
            cid += "x"
        out.append({**c, "id": cid})
    return out


def _register(state: CaseState, agent: str, claims: list[dict]) -> list[dict]:
    done = []
    for c in _claim_ids_unique(state, agent, claims):
        claim = {
            "id": c["id"], "agent": agent, "claim": c["claim"].strip(),
            "evidence": [expand_evidence(state, e) for e in c["evidence"]],
            "confidence": c["confidence"], "innocent_explanation_checked": c["innocent_explanation_checked"],
        }
        state.claims[claim["id"]] = claim
        done.append(claim)
    return done


# --- agents -----------------------------------------------------------------------------

def _planner(state: CaseState, trace: Trace) -> None:
    sl = slices(state)
    user = _dumps({
        "token": {"symbol": state.symbol, "mint": state.mint},
        "summary": sl["deployer"]["summary"],
        "computed": {k: v["value"] for k, v in state.computed.items()},
        "memory": [{"wallet": m["wallet"][:8], "fact": m["fact"]} for m in sl["holders"]["memory"] + sl["deployer"]["memory"]],
    })
    data = call_json(state, trace, agent="planner", step="plan", role="deep", system=prompts.PLANNER, user=user,
                     validate=_v_plan, input_summary="case summary + computed fields + recalled memories")
    state.questions = data["questions"]


def _investigator(state: CaseState, trace: Trace, agent: str) -> list[dict]:
    qs = [q for q in state.questions if q["investigator"] == agent]
    trace.log("investigator_started", agent, {"questions": qs},
              input_summary=f"{len(qs)} question(s) from the planner")
    sl = slices(state)[agent]
    system = (f"You are the {agent} investigator on a Solana token case; you examine "
              f"{prompts.INVESTIGATOR[agent]}. Claim ids start with {PREFIX[agent]}. " + prompts.INVESTIGATOR_RULES)
    base = {"questions": qs, "also_always_check": prompts.CHECKLIST[agent], "evidence": sl,
            "query_tables": table_columns(state)}
    results: list[dict] = []
    for turn in range(MAX_QUERIES + 1):
        payload = {**base, "query_results": results}
        if turn == MAX_QUERIES:
            payload["note"] = "No more queries: answer with action final now."
        data = call_json(state, trace, agent=agent, step="investigate", role="fast", system=system,
                         user=_dumps(payload), validate=_v_investigator,
                         input_summary=f"{len(qs)} question(s), {agent} slice, {len(results)} query result(s)")
        if data["action"] == "final":
            claims = _register(state, agent, data["claims"])
            trace.log("claims", agent, claims, input_summary=f"{len(claims)} claim(s) registered")
            return claims
        if turn == MAX_QUERIES:
            break
        res = query_case(state, trace, agent, data["sql"])
        results.append({"sql": data["sql"], "why": data.get("why"),
                        **({"rows": res["rows"][:40]} if res["ok"] else {"error": res["error"]})})
    raise StepFailed(f"{agent}: no final claims after {MAX_QUERIES} queries")


def _context_for_skeptic(state: CaseState) -> dict:
    s = state.case_file["summary"]
    custodians = {w: [f["content"] for f in fs if f["kind"] == "derived:custodian"]
                  for w, fs in state.memories.items()}
    return {
        "token": {"symbol": state.symbol, "total_holders": s.get("total_holders")},
        "computed": {k: (v["value"] if "note" not in v else {"value": None, "note": v["note"]})
                     for k, v in state.computed.items()},
        "risks": [{"name": r.get("name"), "level": r.get("level"), "value": r.get("value")}
                  for r in state.case_file["risks"]],
        "labelled_holders": [{"owner": h.get("owner"), "pct": h.get("pct"), "label": h.get("label"),
                              "label_type": h.get("label_type")}
                             for h in state.case_file["top_holders"][:20] if h.get("label")],
        "custodian_memories": {w: v for w, v in custodians.items() if v},
    }


def _review(state: CaseState, trace: Trace, claims: list[dict], step: str) -> dict[str, dict]:
    ids = {c["id"] for c in claims}
    user = _dumps({"context": _context_for_skeptic(state), "claims": claims})
    data = call_json(state, trace, agent="skeptic", step=step, role="deep", system=prompts.SKEPTIC, user=user,
                     validate=_v_reviews(ids), input_summary=f"{len(claims)} claim(s) to review")
    out = {}
    for r in data["reviews"]:
        if r.get("id") in ids:
            rec = {"id": r["id"], "decision": r["decision"], "reason": r.get("reason", ""),
                   "fix_request": r.get("fix_request", ""), "round": step}
            state.decisions.setdefault(r["id"], []).append(rec)
            out[r["id"]] = rec
            trace.log("decision", "skeptic", rec, input_summary=state.claims[r["id"]]["claim"])
    return out


def _fix(state: CaseState, trace: Trace, agent: str, rejected: list[dict]) -> list[dict]:
    items = [{"claim": state.claims[r["id"]], "reason": r["reason"], "fix_request": r["fix_request"]}
             for r in rejected]
    user = _dumps({"rejected": items, "evidence": slices(state)[agent]})
    system = f"You are the {agent} investigator. Claim ids start with {PREFIX[agent]}. " + prompts.FIX + \
             "\n" + prompts.INVESTIGATOR_RULES.split("You may first ask")[0]
    data = call_json(state, trace, agent=agent, step="fix", role="fast", system=system, user=user,
                     validate=_v_fix, input_summary=f"{len(items)} rejected claim(s) with fix requests")
    wanted = {r["id"] for r in rejected}
    revised = [c for c in data.get("claims", []) if c.get("id") in wanted]
    for cid in data.get("withdrawn", []) or []:
        if cid in wanted:
            state.dropped.append({"id": cid, "why": "withdrawn by investigator after rejection",
                                  "claim": state.claims[cid]["claim"]})
            trace.log("dropped", agent, state.dropped[-1])
    out = []
    for c in revised:
        claim = {
            "id": c["id"], "agent": agent, "claim": c["claim"].strip(),
            "evidence": [expand_evidence(state, e) for e in c["evidence"]],
            "confidence": c["confidence"], "innocent_explanation_checked": c["innocent_explanation_checked"],
            "revision_of": state.claims[c["id"]]["claim"],
        }
        state.claims[c["id"]] = claim
        out.append(claim)
    trace.log("revised_claims", agent, out)
    return out


def _track(state: CaseState, trace: Trace, agent: str) -> None:
    """One investigator's lane: investigate -> review -> (fix -> re-review) -> drop leftovers."""
    claims = _investigator(state, trace, agent)
    if not claims:
        return
    try:
        first = _review(state, trace, claims, "review")
    except StepFailed as e:
        for c in claims:  # unreviewed claims never reach the verdict
            state.dropped.append({"id": c["id"], "why": "never reviewed (skeptic call failed)",
                                  "claim": c["claim"], "reason": str(e)[:200]})
            trace.log("dropped", "skeptic", state.dropped[-1])
        return
    rejected = [r for r in first.values() if r["decision"] == "reject"]
    if rejected:
        try:
            revised = _fix(state, trace, agent, rejected)
        except StepFailed as e:
            trace.log("fix_failed", agent, {"error": str(e)})
            revised = []
        if revised:
            _review(state, trace, revised, "re_review")
    already = {d["id"] for d in state.dropped}
    for c in claims:
        ds = state.decisions.get(c["id"]) or []
        if c["id"] not in already and (not ds or ds[-1]["decision"] == "reject"):
            state.dropped.append({"id": c["id"], "why": "still rejected after one fix round" if ds else "never reviewed",
                                  "claim": state.claims[c["id"]]["claim"], "reason": ds[-1]["reason"] if ds else ""})
            trace.log("dropped", "skeptic", state.dropped[-1])


def _verdict(state: CaseState, trace: Trace) -> dict:
    accepted = state.accepted()
    ids = {c["id"] for c in accepted}
    user = _dumps({"token": {"symbol": state.symbol, "mint": state.mint},
                   "accepted_claims": [{"id": c["id"], "agent": c["agent"], "claim": c["claim"],
                                        "confidence": c["confidence"],
                                        "evidence": [f"{e['table'].split('.')[-1]}.{e['field']}={e['value']}"
                                                     for e in c["evidence"]]} for c in accepted]})
    data = call_json(state, trace, agent="verdict", step="verdict", role="deep", system=prompts.VERDICT,
                     user=user, validate=_v_verdict(ids), input_summary=f"{len(accepted)} accepted claim(s)")
    data["why"] = [w for w in data["why"] if w["claim_id"] in ids]
    data["models_used"] = sorted(state.models)
    return data


# --- memory -----------------------------------------------------------------------------

def _recall(state: CaseState, trace: Trace) -> None:
    s, holders = state.case_file["summary"], state.case_file["top_holders"][:20]
    wallets = [w for w in [s.get("creator")] + [h.get("owner") for h in holders] if w]
    t = time.time()
    recalled = memory.recall(wallets)
    # Facts this same case wrote on an earlier run are not independent evidence: skip them.
    state.memories = {w: kept for w, fs in recalled.items()
                      if (kept := [f for f in fs if f.get("case_id") != state.case_id])}
    facts = [{"wallet": w, "kind": f["kind"], "fact": f["content"], "source_case": f.get("case_id"),
              "memory_id": f["memory_id"]} for w, fs in state.memories.items() for f in fs]
    trace.log("memory_recall", "h-mem", {"wallets_asked": len(wallets), "wallets_with_memory": len(state.memories),
                                         "facts": facts, "seconds": round(time.time() - t, 2)},
              input_summary="creator + top-20 holder owners")


def _store(state: CaseState, trace: Trace, label: str | None = None, step: str = "memory_store") -> dict:
    """Write this case's wallet facts. At the start of a case the label is PENDING (so the
    custodian derivation can already combine this case with earlier ones); after the verdict
    the same records are updated with the verdict label."""
    s = state.case_file["summary"]
    wallets = []
    if s.get("creator"):
        wallets.append({"wallet": s["creator"], "role": "creator"})
    for i, h in enumerate(state.case_file["top_holders"][:20], 1):
        if not h.get("owner"):
            continue
        if h.get("insider"):
            wallets.append({"wallet": h["owner"], "role": "insider", "rank": i, "pct": h.get("pct")})
        wallets.append({"wallet": h["owner"], "role": "holder", "rank": i, "pct": h.get("pct"),
                        "label": h.get("label")})
    label = label or (state.verdict["label"] if state.verdict else "UNKNOWN")
    res = memory.store(state.case_id, state.mint, state.symbol, state.established, label, wallets)
    trace.log(step, "h-mem", {**{k: len(v) for k, v in res.items()}, "derived_ids": res["derived"],
                                        "established": state.established},
              input_summary=f"{len(wallets)} wallet facts for {state.symbol} (verdict {label})")
    return res


# --- public -----------------------------------------------------------------------------

def _write_json(state: CaseState, name: str, data: Any) -> None:
    d = run_dir(state.case_id, state.run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data, default=str, ensure_ascii=False, indent=1) + "\n")


def investigate(mint: str, on_event: Callable[[dict], None] | None = None,
                run_id: str | None = None) -> CaseState:
    state = _build_state(mint)
    if run_id:
        state.run_id = run_id
    trace = Trace(state, on_event)
    trace.log("start", "casefile", {"mint": state.mint, "symbol": state.symbol,
                                    "snapshot_tables": state.snapshot_tables,
                                    "agent_version": prompts.AGENT_VERSION},
              input_summary="case opened from CASEFILE_SNAP snapshots")
    state.established = bool(computed_fields(state.case_file, {})["established"]["value"])
    _store(state, trace, label="PENDING", step="memory_observe")
    _recall(state, trace)
    state.computed = computed_fields(state.case_file, state.memories)
    trace.log("computed", "casefile", state.computed, input_summary="arithmetic over snapshot fields")
    _write_json(state, "case_file.json", {"case_file": state.case_file, "computed": state.computed,
                                          "snapshot_tables": state.snapshot_tables, "source_urls": state.source_urls,
                                          "established": state.established})

    _planner(state, trace)
    # Pipelined: each investigator's claims go to the skeptic as soon as they exist, then that
    # investigator's single fix round and re-review follow. Zetaris stays serialized by its lock.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {a: pool.submit(_track, state, trace, a) for a in INVESTIGATORS}
        for a, f in futs.items():
            try:
                f.result()
            except StepFailed as e:
                trace.log("investigator_failed", a, {"error": str(e)})

    state.verdict = _verdict(state, trace)
    trace.log("final", "verdict", state.verdict, input_summary="verdict from accepted claims only")
    _store(state, trace)
    stats = {"seconds": round(time.time() - state.started, 1), "llm_calls": state.llm_calls,
             "accepted": len(state.accepted()), "rejected": len({d["id"] for d in state.dropped}),
             "models": sorted(state.models)}
    _write_json(state, "verdict.json", {"run_id": state.run_id, "case_id": state.case_id, "mint": state.mint,
                                        "symbol": state.symbol, "verdict": state.verdict, **stats,
                                        "accepted_claims": state.accepted(), "dropped": state.dropped})
    trace.log("done", "casefile", stats)
    return state
