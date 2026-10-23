"""Python side of H-MEM: calls the TypeScript engine in casefile/hmem through its JSON CLI.

The TypeScript module is the only implementation (it is what the H-MEM conformance suite
checks). Python never writes its state; it sends one request per phase:
  recall(wallets)  at the start of an investigation
  store(case)      after each verdict (also runs the custodian derivation)

State lives in runs/memory/ (state.json + ledger.jsonl), or CASEFILE_HMEM_DIR if set.
A file lock keeps a single writer even if two investigations run at once.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "casefile" / "hmem" / "cli.ts"
TSX = ROOT / "node_modules" / ".bin" / "tsx"


class MemoryError_(RuntimeError):
    pass


def memory_dir() -> Path:
    return Path(os.environ.get("CASEFILE_HMEM_DIR") or ROOT / "runs" / "memory")


def _call(op: str, payload: dict[str, Any]) -> Any:
    if not TSX.exists():
        raise MemoryError_("tsx is not installed: run `npm install` in the repo root.")
    d = memory_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        proc = subprocess.run([str(TSX), str(CLI), op, str(d)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=60, cwd=ROOT)
    line = (proc.stdout.strip().splitlines() or [""])[-1]
    try:
        out = json.loads(line)
    except ValueError:
        raise MemoryError_(f"H-MEM {op} failed: {proc.stderr.strip()[:500] or line[:500]}") from None
    if not out.get("ok"):
        raise MemoryError_(f"H-MEM {op} failed: {out.get('error')}")
    return out["result"]


def recall(wallets: list[str]) -> dict[str, list[dict[str, Any]]]:
    return _call("recall", {"wallets": [w for w in wallets if w]})


def store(case_id: str, mint: str, symbol: str, established: bool, verdict: str,
          wallets: list[dict[str, Any]]) -> dict[str, list[str]]:
    return _call("store", {"case_id": case_id, "mint": mint, "symbol": symbol or "?",
                           "established": bool(established), "verdict": verdict, "wallets": wallets})


def history(memory_id: str) -> list[dict[str, Any]]:
    return _call("history", {"memory_id": memory_id})


def stats() -> dict[str, Any]:
    return _call("stats", {})
