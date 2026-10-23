"""Export one recorded investigation into demo_cases/<case_id>/ for replay without Zetaris/Nightshift.

Usage: uv run python scripts/export_demo_case.py <case_id> [--run <run_id>]
       uv run python scripts/export_demo_case.py --memory      (refresh demo_cases/_memory.json)

Writes trace.jsonl (normalized, docs/TRACE_SCHEMA.md), verdict.json, case_file.json,
receipts.jsonl and meta.json. Secret-like strings are scrubbed and the files are scanned.

Default run choice, in order:
  0. made with the current agent prompts (start event agent_version == prompts.AGENT_VERSION;
     runs from before versions were recorded count if they started after the final rule change,
     CURRENT_RULES_SINCE)
  1. has a verdict
  2. no claims lost to a skeptic failure
  3. fewest retries
  4. most recent
Criteria 0 and 2 are relaxed (and the relaxation printed) only if no run passes them.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from casefile.agents.prompts import AGENT_VERSION  # noqa: E402
from casefile.memory_summary import summary as memory_summary  # noqa: E402
from casefile.trace_schema import normalize, summarize  # noqa: E402

RUNS = ROOT / "runs"
OUT = ROOT / "demo_cases"
CURRENT_RULES_SINCE = "2026-10-23T12:10:00"  # verdict/skeptic rule change before the final proof runs

SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"), re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}"), re.compile(r"\brt-[A-Za-z0-9]{12,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\"?\s*[:=]\s*\"[^\"]{12,}\""),
    re.compile(r"-----BEGIN [A-Z ]+-----"),
]


def _lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _score(run: Path) -> dict:
    raw = _lines(run / "trace.jsonl")
    ev = normalize(raw)
    start = next((r for r in raw if r["step"] == "start"), {})
    version = (start.get("output") or {}).get("agent_version")
    current = version == AGENT_VERSION if version else bool(raw) and raw[0]["ts"] >= CURRENT_RULES_SINCE
    skfail = sum(1 for r in raw if (r["step"] == "investigator_failed" and "skeptic" in str(r["output"]))
                 or (r["step"] == "dropped" and "never reviewed" in str(r["output"])))
    return {"run": run, "run_id": run.name, "started": raw[0]["ts"] if raw else "", "current": current,
            "version": version, "verdict": any(e["type"] == "verdict" for e in ev),
            "skeptic_failures": skfail, "retries": sum(1 for e in ev if e["type"] == "retry")}


def choose(case_id: str) -> tuple[dict, str]:
    runs = [_score(p) for p in sorted((RUNS / case_id).iterdir())
            if p.is_dir() and (p / "trace.jsonl").exists() and not p.name.startswith("_")]
    pool = [r for r in runs if r["verdict"]]
    if not pool:
        raise SystemExit(f"{case_id}: no run has a verdict")
    notes = []
    cur = [r for r in pool if r["current"]]
    if cur:
        pool = cur
    else:
        notes.append("no run made with the current prompts; using older runs")
    clean = [r for r in pool if r["skeptic_failures"] == 0]
    if clean:
        pool = clean
    else:
        notes.append("every candidate lost claims to a skeptic failure")
    pool.sort(key=lambda r: (r["retries"], [-ord(c) for c in r["started"]]))
    best = pool[0]
    why = (f"{len(runs)} runs; {sum(r['verdict'] for r in runs)} with a verdict; "
           f"{sum(1 for r in runs if r['verdict'] and r['current'])} made with the current prompts; "
           f"chose {best['run_id']} (started {best['started'][:19]}Z): verdict, "
           f"{best['skeptic_failures']} skeptic failures, {best['retries']} retries"
           + ("; fewest retries, then most recent" if len(pool) > 1 else "; only candidate")
           + (f"; NOTE: {'; '.join(notes)}" if notes else ""))
    return best, why


def _scrub(text: str) -> tuple[str, int]:
    n = 0
    for pat in SECRET_PATTERNS:
        text, k = pat.subn("[REDACTED]", text)
        n += k
    return text, n


def _write(path: Path, text: str) -> int:
    clean, n = _scrub(text)
    path.write_text(clean)
    return n


def export(case_id: str, run_id: str | None = None) -> dict:
    if run_id:
        run, why = RUNS / case_id / run_id, f"--run {run_id} given"
        if not (run / "trace.jsonl").exists():
            raise SystemExit(f"no run {run_id} for {case_id}")
    else:
        best, why = choose(case_id)
        run = best["run"]
    raw = _lines(run / "trace.jsonl")
    events = normalize(raw)
    summ = summarize(raw)
    verdict = json.loads((run / "verdict.json").read_text())
    cf = json.loads((run / "case_file.json").read_text())
    s = cf["case_file"]["summary"]
    v = verdict.get("verdict") or {}
    meta = {
        "case_id": case_id, "run_id": run.name, "mint": verdict.get("mint") or cf["case_file"]["mint"],
        "symbol": verdict.get("symbol") or s.get("symbol"), "rugcheck_rugged": s.get("rugged"),
        "label": v.get("label"), "one_line": v.get("one_line"),
        "duration_s": (summ["stats"] or {}).get("seconds") or verdict.get("seconds"),
        "llm_calls": (summ["stats"] or {}).get("llm_calls") or verdict.get("llm_calls"),
        "models_used": v.get("models_used") or verdict.get("models"),
        "recorded_at": summ["started_at"], "agent_version": next(
            ((r.get("output") or {}).get("agent_version") for r in raw if r["step"] == "start"), None),
        "events": len(events), "memory_stored": summ["memory_stored"], "selection": why,
    }
    dest = OUT / case_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    redacted = 0
    redacted += _write(dest / "trace.jsonl", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    redacted += _write(dest / "verdict.json", json.dumps(verdict, ensure_ascii=False, indent=1) + "\n")
    redacted += _write(dest / "case_file.json", json.dumps(cf, ensure_ascii=False, indent=1) + "\n")
    if (run / "receipts.jsonl").exists():
        redacted += _write(dest / "receipts.jsonl", (run / "receipts.jsonl").read_text())
    meta["redactions"] = redacted
    _write(dest / "meta.json", json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    return meta


def export_memory() -> dict:
    OUT.mkdir(exist_ok=True)
    m = memory_summary()
    _write(OUT / "_memory.json", json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    return {"wallets": m["wallets"], "custodians": m["custodians"]}


def main() -> int:
    args = sys.argv[1:]
    if args == ["--memory"]:
        print(json.dumps(export_memory()))
        return 0
    if not args:
        print(__doc__)
        return 2
    run_id = args[args.index("--run") + 1] if "--run" in args else None
    meta = export(args[0], run_id)
    print(f"{meta['case_id']} {meta['symbol']}: {meta['label']} (run {meta['run_id']}, {meta['duration_s']} s, "
          f"{meta['llm_calls']} LLM calls, {meta['redactions']} redactions)")
    print(f"  why: {meta['selection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
