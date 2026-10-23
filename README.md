Casefile: agents that explain why a Solana token dumped.

## Pieces

- `casefile/zetaris.py`, `sources.py`, `snapshot.py`, `case_file.py`: the Zetaris data layer.
  RugCheck and DexScreener are Lightning REST tables, shaped by SchemaStore views, frozen once per
  token into `CASEFILE_SNAP` snapshot tables. All Zetaris calls in a process share one lock.
- `casefile/llm.py`: Meterless Nightshift provider. `role="fast"` uses app `casefile-fast`,
  `role="deep"` uses `casefile-deep`; every call's receipt goes to `runs/<case_id>/receipts.jsonl`.
- `casefile/agents/`: planner (deep) -> holders / liquidity / deployer investigators (fast) ->
  skeptic (deep, one fix round) -> verdict (deep). Trace: `runs/<case_id>/trace.jsonl`.
- `casefile/hmem/`: H-MEM memory engine in TypeScript, adapted from the Meterless reference
  (Apache-2.0); `casefile/memory.py` calls it through `casefile/hmem/cli.ts`. State in `runs/memory/`.

## Run it live

The live desk needs a local Zetaris instance (with the `RUGCHECK_REST` / `DEXSCREENER_REST`
Lightning databases), Meterless Nightshift with the `casefile-fast` / `casefile-deep` apps, and the
keys in `.env` (see `.env.example`). Then:

```bash
uv sync && npm install                    # Python deps + tsx for H-MEM
uv run python scripts/check_zetaris.py    # Zetaris up?
uv run python scripts/check_nightshift.py # Nightshift up, roles routed?
uv run python scripts/investigate.py <mint>
uv run python tests/test_hmem.py          # BONK then WIF in fresh processes (live)
uv run pytest tests/ -q                   # API tests in replay mode (no Zetaris/Nightshift)
```

## Web app

Hosted replay (no backend): deploy `web/` to Vercel; `web/vercel.json` builds `npm run build:static`
into `web/dist` from the committed `web/public/demo/`.

```bash
uv run casefile serve            # API + built UI at http://localhost:8000 (serves web/dist-api, committed)
cd web && npm install && npm run dev        # development UI at :5173, proxies /api to :8000
cd web && npm run build                     # web/dist-api for `casefile serve` (VITE_DATA_SOURCE=api)
cd web && npm run build:static              # web/dist: no backend, replays web/public/demo/ (Vercel)
uv run python scripts/build_static_demo.py  # regenerate web/public/demo/ from demo_cases/ via the API
node scripts/ui_check.mjs                   # Playwright check of the static build, screenshots in web/screenshots/
```

The UI is ported from the Claude Design export `design/Casefile.html` (`scripts/unpack_design.py`
unpacks it into `design/src/`). `web/src/data/` has one `DataSource` interface with two sources: `api`
(FastAPI, SSE) and `static` (JSON in `web/public/demo/`, client-side replay with the server's timing).

## API (for the UI)

```bash
uv run casefile serve            # live: http://127.0.0.1:8000, needs Zetaris + Nightshift
uv run casefile serve --replay   # replay only: serves demo_cases/, never calls Zetaris/Nightshift
```

`GET /api/health`, `GET /api/cases`, `GET /api/cases/{case_id}`, `GET /api/cases/{case_id}/trace?run=`,
`GET /api/cases/{case_id}/replay?speed=1|4|16` (SSE), `POST /api/investigate {mint}` (live only),
`GET /api/cases/{case_id}/stream?run=` (SSE, live only), `GET /api/memory`. Event schema:
`docs/TRACE_SCHEMA.md`. Each run lives in `runs/<case_id>/<run_id>/`; recorded demo runs are exported
with `scripts/export_demo_case.py <case_id>` into `demo_cases/` (committed).

H-MEM conformance (from a checkout of github.com/Meterless/Meterless, in `engines/hmem`):
`HMEM_IMPL=$PWD/../../../casefile/casefile/hmem/index.ts npx --yes tsx conformance/runner.ts`
(adjust the path to this repo's `casefile/hmem/index.ts`).

Notes: `fixtures/SOURCES.md` (data fields, snapshots), `fixtures/CASES.md` (rug test cases),
`fixtures/PERF.md` (routing and latency measurements).
