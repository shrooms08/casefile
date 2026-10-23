"""Casefile API: live investigations streamed as they happen, and replay of recorded runs.

  uv run casefile serve            live: Zetaris + Nightshift, POST /api/investigate works
  uv run casefile serve --replay   replay only: reads demo_cases/, never calls Zetaris/Nightshift

SSE streams send one `data: <event json>` message per normalized trace event (docs/TRACE_SCHEMA.md),
with `id: <seq>`, and finish with `data: {"type": "done", ...}`.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from casefile.server.store import Store, _lines, case_summary
from casefile.trace_schema import normalize, summarize

REPLAY_SPEEDS = (1, 4, 16)
MAX_GAP_S = 2.5
POLL_S = 0.5


class InvestigateBody(BaseModel):
    mint: str


def _ts(s: str | None) -> float | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _sse(obj: dict, event_id: Any = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return head + "data: " + json.dumps(obj, default=str, ensure_ascii=False) + "\n\n"


class Worker:
    """One live investigation at a time, in a background thread."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.current: dict | None = None

    def busy(self) -> dict | None:
        with self.lock:
            return dict(self.current) if self.current else None

    def start(self, mint: str, case_id: str, store: Store) -> dict:
        with self.lock:
            if self.current:
                return {"busy": dict(self.current)}
            run_id = uuid.uuid4().hex[:10]
            self.current = {"case_id": case_id, "run_id": run_id, "mint": mint,
                            "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"}
        threading.Thread(target=self._run, args=(mint, case_id, run_id, store), daemon=True,
                         name=f"investigate-{run_id}").start()
        return {"case_id": case_id, "run_id": run_id}

    def _run(self, mint: str, case_id: str, run_id: str, store: Store) -> None:
        try:
            from casefile.agents.loop import investigate  # live-only import
            investigate(mint, run_id=run_id)
        except Exception as e:  # recorded so the stream can end with an error event
            p = store.raw_path(case_id, run_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a") as f:
                f.write(json.dumps({"ts": datetime.utcnow().isoformat(timespec="milliseconds") + "+00:00",
                                    "run_id": run_id, "case_id": case_id, "seq": 0, "step": "run_failed",
                                    "agent": "casefile", "model": None, "receipt_id": None, "sql": None,
                                    "input_summary": "investigation stopped",
                                    "output": {"error": f"{type(e).__name__}: {str(e)[:500]}"}}) + "\n")
        finally:
            with self.lock:
                self.current = None

    def running_run_id(self) -> str | None:
        b = self.busy()
        return b["run_id"] if b else None


def create_app(replay: bool = False, store: Store | None = None) -> FastAPI:
    app = FastAPI(title="Casefile API", version="0.3.0")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3001"],
                       allow_methods=["*"], allow_headers=["*"])
    store = store or Store(replay=replay)
    worker = Worker()
    app.state.store, app.state.worker, app.state.replay = store, worker, replay

    def _run_or_404(case_id: str, run_id: str | None = None):
        r = store.run(case_id, run_id, worker.running_run_id())
        if not r:
            raise HTTPException(404, f"no {'run ' + run_id + ' for ' if run_id else ''}case {case_id}")
        return r

    @app.get("/api/health")
    def health() -> dict:
        if replay:
            return {"mode": "replay", "zetaris": "n/a", "nightshift": "n/a"}

        def check(fn, timeout: float) -> str:
            box: dict = {}

            def go():
                try:
                    box["ok"] = fn()
                except Exception:
                    box["ok"] = False
            t = threading.Thread(target=go, daemon=True)
            t.start()
            t.join(timeout)
            return "ok" if box.get("ok") else "down"

        def zetaris_ok() -> bool:
            from casefile.zetaris import run_sql
            return run_sql("SELECT 1 AS one")[0]["one"] == "1"

        def nightshift_ok() -> bool:
            from casefile import llm
            return llm.status() == "online"

        return {"mode": "live", "zetaris": check(zetaris_ok, 20), "nightshift": check(nightshift_ok, 15),
                "investigation_running": worker.busy()}

    @app.get("/api/cases")
    def cases() -> list[dict]:
        out = []
        for cid in store.case_ids():
            r = store.run(cid, running=worker.running_run_id())
            if r:
                out.append({**r.meta, "runs": store.run_ids(cid) or [r.run_id]})
        return out

    @app.get("/api/cases/{case_id}")
    def case(case_id: str, run: str | None = None) -> dict:
        r = _run_or_404(case_id, run)
        return {"meta": r.meta, "verdict": r.verdict, "summary": case_summary(r.case_file),
                "runs": store.run_ids(case_id) or [r.run_id]}

    @app.get("/api/cases/{case_id}/trace")
    def trace(case_id: str, run: str | None = None) -> dict:
        r = _run_or_404(case_id, run)
        return {"case_id": case_id, "run_id": r.run_id, "source": r.source, "summary": r.summary,
                "events": r.events}

    @app.get("/api/cases/{case_id}/replay")
    async def replay_stream(case_id: str, speed: int = Query(4), run: str | None = None,
                            from_seq: int = Query(0, alias="from", ge=0)):
        """Recorded run as SSE. `from=<seq>` resumes after that event (pause / speed change / seek)."""
        if speed not in REPLAY_SPEEDS:
            raise HTTPException(400, f"speed must be one of {REPLAY_SPEEDS}")
        r = _run_or_404(case_id, run)
        events = [e for e in r.events if e["seq"] > from_seq]
        prev_ts = next((e.get("ts") for e in r.events if e["seq"] == from_seq), None)

        async def gen():
            prev = _ts(prev_ts)
            yield ": casefile replay\n\n"
            for e in events:
                t = _ts(e.get("ts"))
                if prev is not None and t is not None:
                    await asyncio.sleep(min(max(t - prev, 0) / speed, MAX_GAP_S))
                prev = t if t is not None else prev
                yield _sse(e, e["seq"])
            yield _sse({"type": "done", "case_id": case_id, "run_id": r.run_id, "summary": r.summary,
                        "replay_speed": speed})
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/investigate")
    def investigate(body: InvestigateBody):
        if replay:
            return JSONResponse(status_code=403, content={
                "detail": "This server is in replay mode, so it can't start new investigations. "
                          "Watch a recorded case with GET /api/cases/{case_id}/replay, or run "
                          "`uv run casefile serve` with Zetaris and Nightshift for live mode."})
        from casefile.sources import case_id as cid_for, validate_mint
        try:
            mint = validate_mint(body.mint)
        except ValueError as e:
            raise HTTPException(422, str(e))
        res = worker.start(mint, cid_for(mint), store)
        if "busy" in res:
            return JSONResponse(status_code=409, content={
                "detail": "An investigation is already running; one at a time.", "running": res["busy"]})
        return res

    @app.get("/api/cases/{case_id}/stream")
    async def stream(case_id: str, run: str | None = None):
        if replay:
            raise HTTPException(403, "live streams are not available in replay mode; use /replay")
        busy = worker.busy()
        run_id = run or (busy["run_id"] if busy and busy["case_id"] == case_id else None)
        if not run_id:
            ids = store.run_ids(case_id)
            if not ids:
                raise HTTPException(404, f"no run for case {case_id}")
            run_id = ids[-1]
        path = store.raw_path(case_id, run_id)

        async def gen():
            sent, last_beat = 0, time.time()
            yield ": casefile live stream\n\n"
            while True:
                raw = _lines(path)
                events = normalize(raw)
                for e in events[sent:]:
                    yield _sse(e, e["seq"])
                sent = len(events)
                finished = any(x.get("step") in ("done", "run_failed") for x in raw)
                still_running = worker.running_run_id() == run_id
                if finished or (not still_running and raw):
                    summ = summarize(raw)
                    if not finished:
                        summ["note"] = "run is not running and has no done event (stopped earlier)"
                    yield _sse({"type": "done", "case_id": case_id, "run_id": run_id, "summary": summ,
                                "status": "done" if any(x.get("step") == "done" for x in raw) else "failed"})
                    return
                if not still_running and not raw:
                    yield _sse({"type": "done", "case_id": case_id, "run_id": run_id, "status": "missing"})
                    return
                if time.time() - last_beat > 15:
                    last_beat = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(POLL_S)
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/memory")
    def memory() -> dict:
        return store.memory()

    _mount_web(app)
    return app


WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def _mount_web(app: FastAPI, dist: Path = WEB_DIST) -> None:
    """Serve the built UI (web/dist) at /, with client-side routes falling back to index.html."""
    index = dist / "index.html"
    if not index.exists():
        return

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "not found")
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(index)
