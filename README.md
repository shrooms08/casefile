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

## Run

```bash
uv sync && npm install                    # Python deps + tsx for H-MEM
uv run python scripts/check_zetaris.py    # Zetaris up?
uv run python scripts/check_nightshift.py # Nightshift up, roles routed?
uv run python scripts/investigate.py <mint>
uv run python tests/test_hmem.py          # BONK then WIF in fresh processes
```

H-MEM conformance (from a checkout of github.com/Meterless/Meterless, in `engines/hmem`):
`HMEM_IMPL=$PWD/../../../casefile/casefile/hmem/index.ts npx --yes tsx conformance/runner.ts`
(adjust the path to this repo's `casefile/hmem/index.ts`).

Notes: `fixtures/SOURCES.md` (data fields, snapshots), `fixtures/CASES.md` (rug test cases),
`fixtures/PERF.md` (routing and latency measurements).
