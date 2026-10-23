"""Read-only H-MEM summary for the UI.

Reads the TypeScript engine's state.json directly (never writes it, never touches access counts
or the ledger, unlike a recall). Per wallet: how many cases it appears in, roles, tokens, and any
"likely custodian or exchange" notes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from casefile.memory import memory_dir


def _tag(tags: list[str], key: str) -> str | None:
    return next((t[len(key) + 1:] for t in tags if t.startswith(f"{key}:")), None)


def summarize_state(state: dict) -> dict[str, Any]:
    wallets: dict[str, dict[str, Any]] = defaultdict(lambda: {"cases": set(), "roles": set(), "tokens": set(),
                                                              "verdicts": {}, "custodian_notes": []})
    records = state.get("records") or []
    for m in records:
        tags = m.get("tags") or []
        w = _tag(tags, "wallet")
        if not w:
            continue
        row = wallets[w]
        if "derived:custodian" in tags:
            if not m.get("supersededBy"):
                row["custodian_notes"].append({"memory_id": m["id"], "note": m["content"],
                                               "derived_from": m.get("derivedFrom") or []})
            continue
        case, token = _tag(tags, "case"), _tag(tags, "token")
        if case:
            row["cases"].add(case)
            row["verdicts"][case] = _tag(tags, "verdict")
        if token:
            row["tokens"].add(token)
        if _tag(tags, "role"):
            row["roles"].add(_tag(tags, "role"))
    out = []
    for w, row in wallets.items():
        out.append({"wallet": w, "case_count": len(row["cases"]), "cases": sorted(row["cases"]),
                    "roles": sorted(row["roles"]), "tokens": sorted(row["tokens"]),
                    "verdicts": row["verdicts"], "likely_custodian": bool(row["custodian_notes"]),
                    "custodian_notes": row["custodian_notes"]})
    out.sort(key=lambda r: (not r["likely_custodian"], -r["case_count"], r["wallet"]))
    return {"records": len(records), "wallets": len(out),
            "custodians": sum(1 for r in out if r["likely_custodian"]),
            "multi_case_wallets": sum(1 for r in out if r["case_count"] >= 2), "items": out}


def summary(path: Path | None = None) -> dict[str, Any]:
    p = path or memory_dir() / "state.json"
    if not p.exists():
        return {"records": 0, "wallets": 0, "custodians": 0, "multi_case_wallets": 0, "items": [],
                "note": f"no H-MEM state at {p}"}
    return summarize_state(json.loads(p.read_text()))
