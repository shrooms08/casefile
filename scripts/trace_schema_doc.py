"""Regenerate docs/TRACE_SCHEMA.md: one real example per event type from demo_cases/ and runs/.

Types no recorded run has used yet (sql_query, fallback) get an example built through the same
normalizer from a hand-written raw event, marked "example_only": true.

Usage: uv run python scripts/trace_schema_doc.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from casefile.trace_schema import TYPES, normalize  # noqa: E402

HEAD = '# Casefile trace schema (v1)\n\nThe UI reads investigations as a list of **normalized trace events**. The agents write raw events to\n`runs/<case_id>/<run_id>/trace.jsonl`; `casefile/trace_schema.py` turns them into this schema. The same\nevents come from `GET /api/cases/{case_id}/trace`, the replay SSE and the live SSE.\n\n## Event\n\n| Field | Type | Meaning |\n|---|---|---|\n| `seq` | int | 1, 2, 3... within the run, no gaps |\n| `ts` | ISO 8601 string | when it happened (UTC) |\n| `run_id` | string | one investigation |\n| `case_id` | string | `m_` + sha1(mint)[:12] |\n| `type` | string | one of the 13 types below |\n| `agent` | string | `casefile`, `h-mem`, `planner`, `holders`, `liquidity`, `deployer`, `skeptic`, `verdict` |\n| `model` | string or null | routed model for LLM steps (e.g. `nvidia/nemotron-3.5-super-vl-120b-a12b`) |\n| `receipt_id` | string or null | Meterless receipt for that LLM call |\n| `title` | string | one short human-readable line |\n| `detail` | object | type-specific fields (below) |\n\nNormalization is prefix-stable: events for the first N raw lines never change when more lines arrive.\n\n## SSE\n\n`/replay` and `/stream` send one message per event: `id: <seq>` and `data: <event JSON>`. The last\nmessage is `data: {"type": "done", "case_id", "run_id", "summary": {...}}`, which is not a trace event.\nFor a finished run the message before `done` is the `verdict` (or an `error` if the run stopped).\nReplay keeps the recorded gaps divided by `speed` (1, 4 or 16), with any single gap capped at 2.5 s.\nLines starting with `:` are keep-alive comments.\n\n## Types\n'
WHEN = {
 "case_opened": "The run starts: the case file was read from the frozen CASEFILE_SNAP snapshot tables.",
 "memory_recalled": "H-MEM recall for the creator and top-20 holders. `facts` are prior-case facts and derived notes; `custodian_wallets` lists wallets H-MEM marks likely custodian or exchange; `observed_this_case` is what was written for this case before recall (verdict PENDING).",
 "plan": "The planner (deep model) wrote its questions. `computed` holds the arithmetic fields it saw.",
 "investigator_started": "One per investigator (holders, liquidity, deployer), with its questions. For runs recorded before agent versions existed this is derived from the plan (`detail.synthesized: true`).",
 "sql_query": "An investigator used `query_case` (read-only SELECT on this case's snapshot tables). `ok: false` means the query was refused or failed (`error`). No recorded demo run has one yet, so the example shape below is labelled `example_only`.",
 "claim": "An investigator's claim, with its evidence. Each evidence item carries `verified` and `check` from the mechanical lookup against the snapshot data. A revised claim has `revision_of` (the earlier wording).",
 "skeptic_decision": "The skeptic (deep model) accepts or rejects one claim. `round` is `review` or `re_review`.",
 "rework_requested": "Follows a first-round rejection: the claim goes back to its investigator once with `fix_request`.",
 "claim_dropped": "A claim that will not reach the verdict: withdrawn after rejection, still rejected after the one fix round, or never reviewed.",
 "retry": "An LLM call failed (`kind: call failed`, e.g. Nightshift's 45 s abort or an NVIDIA 500) or returned invalid JSON (`kind: invalid output`) and is being retried.",
 "fallback": "A deep-model step kept timing out and gets one try on the fast model. No recorded demo run needed one yet, so the example below is labelled `example_only`.",
 "verdict": "The final verdict from accepted claims only. Every `why` item names an accepted `claim_id`.",
 "error": "A step failed for good (e.g. an investigator whose skeptic review failed every retry) or the run stopped (`step: run_failed`)."
}


def trim(o, n=3):
    if isinstance(o, dict):
        return {k: trim(v, n) for k, v in o.items()}
    if isinstance(o, list):
        return [trim(v, n) for v in o[:n]] + (["…"] if len(o) > n else [])
    if isinstance(o, str) and len(o) > 160:
        return o[:157] + "…"
    return o


def main() -> int:
    ex: dict[str, dict] = {}
    files = [ROOT / "demo_cases/m_bd95541d260d/trace.jsonl"] + [Path(f) for f in sorted(glob.glob(str(ROOT / "demo_cases/m_*/trace.jsonl")))]
    for p in files:
        for line in p.read_text().splitlines():
            e = json.loads(line)
            ex.setdefault(e["type"], e)
    for f in sorted(glob.glob(str(ROOT / "runs/m_*/*/trace.jsonl"))):
        for e in normalize([json.loads(l) for l in Path(f).read_text().splitlines() if l.strip()]):
            ex.setdefault(e["type"], e)
    base = {"ts": "2026-10-23T14:46:02.120+00:00", "run_id": "d96d0118ff", "case_id": "m_bd95541d260d",
            "model": None, "receipt_id": None}
    for e in normalize([
        {**base, "step": "query", "agent": "holders",
         "sql": "SELECT owner, pct, label FROM casefile_snap.m_bd95541d260d_holders_labelled_snap WHERE label IS NULL ORDER BY pct DESC",
         "output": {"rows": 3, "sample": [{"owner": "9UnZnrFJ1CXCmCorgGU9NvYkX5np1h4v4ympx3Nrdw3v", "pct": "0.2456", "label": None}]}},
        {**base, "step": "verdict_fallback", "agent": "verdict",
         "output": {"from": "deep", "to": "fast", "reason": "Meterless stream error: request_aborted"}},
    ]):
        e["detail"]["example_only"] = True
        ex.setdefault(e["type"], e)
    out = [HEAD]
    for t in TYPES:
        out.append(f"### `{t}`\n\n{WHEN[t]}\n\n```json\n{json.dumps(trim(ex[t]), ensure_ascii=False, indent=1)}\n```\n")
    (ROOT / "docs" / "TRACE_SCHEMA.md").write_text("\n".join(out))
    print(f"wrote docs/TRACE_SCHEMA.md with {len(TYPES)} types")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
