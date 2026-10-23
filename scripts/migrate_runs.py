"""Move pre-Day-3 runs into the one-directory-per-run layout. Safe to re-run.

Before: runs/<case_id>/trace.jsonl (all runs appended) and runs/<case_id>/receipts.jsonl.
After:  runs/<case_id>/<run_id>/{trace.jsonl, receipts.jsonl, verdict.json, case_file.json}.

- trace lines are split by run_id, order kept
- a receipt goes to the run whose trace names its receipt_id, else the run whose time window
  (first event .. last event + 10 s) contains it; the rest go to runs/<case_id>/_unassigned/
- verdict.json comes from the run's "final" + "done" events (runs that crashed get none)
- case_file.json is rebuilt from the frozen CASEFILE_SNAP snapshot through Zetaris (the same
  rows the agents read), marked "reconstructed": true, with the computed fields the run logged
- the old files are kept, renamed trace.legacy.jsonl / receipts.legacy.jsonl

Usage: uv run python scripts/migrate_runs.py [--no-case-file]
"""

from __future__ import annotations

import json
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def migrate_case(case_dir: Path, with_case_file: bool) -> dict:
    legacy_trace = case_dir / "trace.legacy.jsonl"
    src_trace = case_dir / "trace.jsonl" if (case_dir / "trace.jsonl").exists() else legacy_trace
    events = _lines(src_trace)
    if not events:
        return {"case": case_dir.name, "runs": 0}
    runs: "OrderedDict[str, list[dict]]" = OrderedDict()
    for e in events:
        runs.setdefault(e["run_id"], []).append(e)

    receipts = _lines(case_dir / "receipts.jsonl") + _lines(case_dir / "receipts.legacy.jsonl")
    by_receipt = {e["receipt_id"]: rid for rid, evs in runs.items() for e in evs if e.get("receipt_id")}
    windows = {rid: (_ts(evs[0]["ts"]), _ts(evs[-1]["ts"]) + 10) for rid, evs in runs.items()}
    assigned: dict[str, list[dict]] = {rid: [] for rid in runs}
    unassigned = []
    for r in receipts:
        rid = by_receipt.get(r.get("receipt_id"))
        if not rid and r.get("at"):
            t = _ts(r["at"])
            rid = next((k for k, (a, b) in windows.items() if a <= t <= b), None)
        (assigned[rid] if rid else unassigned).append(r)

    cf_cache = None
    out = []
    for rid, evs in runs.items():
        d = case_dir / rid
        d.mkdir(exist_ok=True)
        if not (d / "trace.jsonl").exists():
            (d / "trace.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evs))
        if assigned[rid] and not (d / "receipts.jsonl").exists():
            (d / "receipts.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in assigned[rid]))
        final = next((e for e in evs if e["step"] == "final"), None)
        done = next((e for e in evs if e["step"] == "done"), None)
        start = next((e for e in evs if e["step"] == "start"), None)
        if final and not (d / "verdict.json").exists():
            claims = {c["id"]: c for e in evs if e["step"] in ("claims", "revised_claims") for c in e["output"]}
            last = {}
            for e in evs:
                if e["step"] == "decision":
                    last[e["output"]["id"]] = e["output"]["decision"]
            dropped = [e["output"] for e in evs if e["step"] == "dropped"]
            (d / "verdict.json").write_text(json.dumps({
                "run_id": rid, "case_id": case_dir.name,
                "mint": (start or {}).get("output", {}).get("mint"),
                "symbol": (start or {}).get("output", {}).get("symbol"),
                "verdict": final["output"], **((done or {}).get("output") or {}),
                "accepted_claims": [c for cid, c in claims.items() if last.get(cid) == "accept"],
                "dropped": dropped, "migrated": True,
            }, ensure_ascii=False, indent=1) + "\n")
        if with_case_file and start and not (d / "case_file.json").exists():
            if cf_cache is None:
                from casefile.case_file import get_case_file
                from casefile.sources import _load_registry
                mint = start["output"]["mint"]
                reg = _load_registry().get(mint, {})
                cf_cache = (get_case_file(mint), reg.get("urls", {}))
            computed = next((e["output"] for e in evs if e["step"] == "computed"), {})
            (d / "case_file.json").write_text(json.dumps({
                "case_file": cf_cache[0], "computed": computed,
                "snapshot_tables": start["output"].get("snapshot_tables"), "source_urls": cf_cache[1],
                "established": (computed.get("established") or {}).get("value"),
                "reconstructed": True,
                "note": "rebuilt from the frozen snapshot after the run; same rows the agents read "
                        "(runs before 2026-10-23 ~13:00 UTC saw null fields omitted)",
            }, default=str, ensure_ascii=False, indent=1) + "\n")
        out.append({"run_id": rid, "events": len(evs), "receipts": len(assigned[rid]), "verdict": bool(final)})

    if unassigned:
        u = case_dir / "_unassigned"
        u.mkdir(exist_ok=True)
        (u / "receipts.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in unassigned))
    for name in ("trace", "receipts"):
        cur, leg = case_dir / f"{name}.jsonl", case_dir / f"{name}.legacy.jsonl"
        if cur.exists() and not leg.exists():
            cur.rename(leg)
    return {"case": case_dir.name, "runs": len(runs), "unassigned_receipts": len(unassigned), "detail": out}


def main() -> int:
    with_cf = "--no-case-file" not in sys.argv
    for case_dir in sorted(RUNS.glob("m_*")):
        if (case_dir / "trace.jsonl").exists() or (case_dir / "trace.legacy.jsonl").exists():
            print(json.dumps(migrate_case(case_dir, with_cf)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
