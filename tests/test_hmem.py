"""H-MEM across investigations, in fresh processes.

1. With an empty memory dir, investigate BONK in one process.
2. In a second process, investigate WIF.
3. WIF's recall must include the two top holders BONK and WIF share, from the BONK case, and
   both must carry the derived "likely custodian or exchange" note.

Run: uv run python tests/test_hmem.py   (or: CASEFILE_LIVE_TESTS=1 uv run pytest tests/test_hmem.py)
Takes several minutes: two full investigations through Zetaris and Nightshift, so pytest skips it
unless CASEFILE_LIVE_TESTS=1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
SHARED = ("51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")


def _investigate(mint: str, env: dict) -> dict:
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "investigate.py"), mint, "--json"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=1200)
    assert out.returncode == 0, f"investigate {mint} failed:\n{out.stdout[-2000:]}\n{out.stderr[-2000:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def _last_run_events(case_id: str) -> list[dict]:
    runs = [p for p in (ROOT / "runs" / case_id).iterdir() if (p / "trace.jsonl").exists()]
    latest = max(runs, key=lambda p: (p / "trace.jsonl").stat().st_mtime)
    return [json.loads(l) for l in (latest / "trace.jsonl").read_text().splitlines() if l]


@pytest.mark.skipif(os.environ.get("CASEFILE_LIVE_TESTS") != "1" and __name__ != "__main__",
                    reason="live test: set CASEFILE_LIVE_TESTS=1 (needs Zetaris + Nightshift)")
def test_wif_recalls_bonk_custodians() -> None:
    mem = tempfile.mkdtemp(prefix="hmem-test-")
    env = {**os.environ, "CASEFILE_HMEM_DIR": mem, "PYTHONUNBUFFERED": "1"}

    bonk = _investigate(BONK, env)
    assert bonk["verdict"]["label"] in ("NO_RUG_EVIDENCE", "CAUTION"), bonk["verdict"]
    wif = _investigate(WIF, env)

    from casefile.sources import case_id
    events = _last_run_events(case_id(WIF))
    recall = next(e for e in events if e["step"] == "memory_recall")["output"]
    facts = recall["facts"]
    bonk_case = case_id(BONK)
    for wallet in SHARED:
        mine = [f for f in facts if f["wallet"] == wallet]
        assert any(f["kind"] == "wallet_fact" and f["source_case"] == bonk_case for f in mine), \
            f"WIF did not recall BONK's fact for {wallet}: {mine}"
        assert any(f["kind"] == "derived:custodian" and "likely a custodian or exchange" in f["fact"] for f in mine), \
            f"{wallet} is not marked likely custodian: {mine}"
    print(json.dumps({"memory_dir": mem, "bonk": bonk["verdict"]["label"], "wif": wif["verdict"]["label"],
                      "wif_recall": [f for f in facts if f["wallet"] in SHARED]}, indent=2))


if __name__ == "__main__":
    test_wif_recalls_bonk_custodians()
    print("PASS test_wif_recalls_bonk_custodians")
