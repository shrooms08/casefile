"""Build web/public/demo/ for the static (no-backend) web build.

Copies demo_cases/* into web/public/demo/ and writes the JSON the static data source reads, produced
by calling the real API in replay mode so the shapes match exactly:

  demo/health.json            GET /api/health        (mode rewritten to "static")
  demo/cases.json             GET /api/cases
  demo/<case_id>/case.json    GET /api/cases/{case_id}
  demo/<case_id>/trace.json   GET /api/cases/{case_id}/trace
  demo/memory.json            GET /api/memory

Usage: uv run python scripts/build_static_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from casefile.server.app import create_app  # noqa: E402
from casefile.server.store import DEMO  # noqa: E402

OUT = ROOT / "web" / "public" / "demo"


def _get(client: TestClient, url: str):
    r = client.get(url)
    r.raise_for_status()
    return r.json()


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    client = TestClient(create_app(replay=True))

    health = _get(client, "/api/health")
    _dump(OUT / "health.json", {**health, "mode": "static"})
    cases = _get(client, "/api/cases")
    _dump(OUT / "cases.json", cases)
    for c in cases:
        cid = c["case_id"]
        shutil.copytree(DEMO / cid, OUT / cid)            # the exported files themselves
        _dump(OUT / cid / "case.json", _get(client, f"/api/cases/{cid}"))
        _dump(OUT / cid / "trace.json", _get(client, f"/api/cases/{cid}/trace"))
    _dump(OUT / "memory.json", _get(client, "/api/memory"))
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"wrote {OUT.relative_to(ROOT)}: {len(cases)} cases, {size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
