"""API tests in replay mode: demo_cases only, no Zetaris, no Nightshift.

Run: uv run pytest tests/test_api.py -q
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from casefile.server.app import create_app
from casefile.server.store import DEMO
from casefile.trace_schema import TYPES

CASES = sorted(p.name for p in DEMO.iterdir() if (p / "meta.json").exists())
YAGI = "m_bd95541d260d"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(replay=True))


def test_demo_cases_exist():
    assert {"m_d54bf9a14eb4", "m_d2f031d73387", "m_bd95541d260d", "m_0c961a12701d"} <= set(CASES)


def test_health_replay(client):
    assert client.get("/api/health").json() == {"mode": "replay", "zetaris": "n/a", "nightshift": "n/a"}


def test_cases_list(client):
    rows = client.get("/api/cases").json()
    assert sorted(r["case_id"] for r in rows) == CASES
    for r in rows:
        assert r["source"] == "demo" and r["label"] and r["mint"] and r["run_id"]
        for k in ("symbol", "rugcheck_rugged", "one_line", "duration_s", "llm_calls", "models_used", "recorded_at"):
            assert k in r


@pytest.mark.parametrize("case_id", CASES)
def test_case_detail(client, case_id):
    d = client.get(f"/api/cases/{case_id}").json()
    s = d["summary"]
    assert d["verdict"]["verdict"]["label"] == d["meta"]["label"]
    assert s["best_pair"]["dex"] and s["best_pair"]["liquidity_usd"] is not None
    assert "price_change_24h" in s["best_pair"] and "volume_24h" in s["best_pair"]
    assert isinstance(s["holders"], int) and 1 <= len(s["top_holders"]) <= 10
    assert set(s["top_holders"][0]) == {"owner", "pct", "insider", "label", "label_type"}
    assert "count" in s["insider_networks"] and "mint_authority" in s["authorities"]
    assert s["sources"] and all(x["zetaris_view"].startswith("casefile.") and x["api_url"].startswith("https://")
                                for x in s["sources"])


def test_case_404(client):
    assert client.get("/api/cases/m_nope").status_code == 404


@pytest.mark.parametrize("case_id", CASES)
def test_trace_schema(client, case_id):
    t = client.get(f"/api/cases/{case_id}/trace").json()
    ev = t["events"]
    assert ev and [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
    for e in ev:
        assert set(e) == {"seq", "ts", "run_id", "case_id", "type", "agent", "model", "receipt_id", "title", "detail"}
        assert e["type"] in TYPES and e["title"] and isinstance(e["detail"], dict)
        assert e["run_id"] == t["run_id"] and e["case_id"] == case_id
    assert ev[0]["type"] == "case_opened" and ev[-1]["type"] == "verdict"
    assert client.get(f"/api/cases/{case_id}/trace", params={"run": t["run_id"]}).status_code == 200
    assert client.get(f"/api/cases/{case_id}/trace", params={"run": "nope"}).status_code == 404


def test_wif_trace_shows_custodian_memory(client):
    ev = client.get("/api/cases/m_d2f031d73387/trace").json()["events"]
    mem = next(e for e in ev if e["type"] == "memory_recalled")
    assert {"51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j",
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"} <= set(mem["detail"]["custodian_wallets"])


def test_replay_bad_speed(client):
    assert client.get(f"/api/cases/{YAGI}/replay", params={"speed": 3}).status_code == 400


def test_replay_sse_speed16(client):
    n_events = len(client.get(f"/api/cases/{YAGI}/trace").json()["events"])
    got = []
    with client.stream("GET", f"/api/cases/{YAGI}/replay", params={"speed": 16}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                got.append(json.loads(line[6:]))
                if got[-1]["type"] == "done":
                    break
    assert got[-1]["type"] == "done" and got[-2]["type"] == "verdict"
    assert got[-2]["detail"]["label"] in ("RUGGED", "HIGH_RISK")
    assert len(got) == n_events + 1


def test_investigate_forbidden_in_replay(client):
    r = client.post("/api/investigate", json={"mint": "FxzUDJHc9TbMJjGmthmnjbC9AF6FnGxNuFmbP1Jepump"})
    assert r.status_code == 403 and "replay mode" in r.json()["detail"]


def test_stream_forbidden_in_replay(client):
    assert client.get(f"/api/cases/{YAGI}/stream").status_code == 403


def test_memory(client):
    m = client.get("/api/memory").json()
    assert m["wallets"] > 0 and m["custodians"] >= 2
    row = next(r for r in m["items"] if r["wallet"] == "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM")
    assert row["likely_custodian"] and row["case_count"] >= 2 and "holder" in row["roles"]


def test_cors(client):
    r = client.options("/api/cases", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
