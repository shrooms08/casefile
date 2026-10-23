# Test results

Recorded on 2026-10-23 against commit `ee59e3d` plus this documentation change (no code changed).

| Suite | Command | Result |
|---|---|---|
| API (replay mode) | `uv run pytest tests -q` | 21 passed, 1 skipped in 24.30s |
| UI (static build, Playwright) | `cd web && npm run build:static && cd .. && node scripts/ui_check.mjs` | UI CHECK PASSED: 64 checks ok, 0 failures |
| H-MEM conformance | `HMEM_IMPL=<repo>/casefile/hmem/index.ts npx --yes tsx conformance/runner.ts` (Meterless `engines/hmem`, commit `1742dec`) | 13/13 checks passed |
| H-MEM live (Zetaris + Nightshift) | `CASEFILE_LIVE_TESTS=1 uv run pytest tests/test_hmem.py -s` | 1 passed in 913.57s (0:15:13) |

The skipped pytest test is the live H-MEM test, which only runs with `CASEFILE_LIVE_TESTS=1` (last row).
The UI check against `vite preview` (the exact Vercel build flow, including deep-link refresh) also passed in the
previous step (commit `ee59e3d`).

## H-MEM conformance checks

- PASS rv-001 a record with no source is rejected by construction
- PASS rv-002 a record with a source is accepted
- PASS fd-001 helpful adds exactly +0.05 confidence and +1 accessCount
- PASS fd-002 not_helpful subtracts exactly 0.03
- PASS fd-003 wrong subtracts exactly 0.20 and adds the review tag
- PASS fd-004 confidence clamps at 0 (wrong at 0.1)
- PASS fd-005 confidence clamps at 1 (helpful at 0.98)
- PASS ro-001 superseded penalty dominates: a superseded record ranks below a fresh one with identical content relevance
- PASS ro-002 confidence multiplies the whole score: identical records rank by confidence
- PASS sg-001 old low-access plain record archives; dream-derived record with identical age does not
- PASS cg-001 auto-resolve marks the loser supersededBy and deletes nothing
- PASS la-001 create then feedback reconstructs: actions in order, previous and new confidence present
- PASS db-001 dream proposals never materialize before approval; approval creates a long_term record with lineage

## H-MEM live test

Fresh processes, empty memory folder: BONK verdict **CAUTION**, then WIF verdict **CAUTION**. WIF recalled:

```json
[
 {
  "wallet": "51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j",
  "kind": "wallet_fact",
  "source_case": "m_d54bf9a14eb4",
  "fact": "wallet 51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j was top holder rank 2 at 6.79 pct of token bonk (mint DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263) in case m_d54bf9a14eb4; established=true; verdict caution"
 },
 {
  "wallet": "51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j",
  "kind": "derived:custodian",
  "source_case": null,
  "fact": "wallet 51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j is likely a custodian or exchange: top holder of 2 different established tokens ($wif, bonk)"
 },
 {
  "wallet": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
  "kind": "wallet_fact",
  "source_case": "m_d54bf9a14eb4",
  "fact": "wallet 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM was top holder rank 1 at 8.83 pct of token bonk (mint DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263) in case m_d54bf9a14eb4; established=true; verdict caution"
 },
 {
  "wallet": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
  "kind": "derived:custodian",
  "source_case": null,
  "fact": "wallet 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM is likely a custodian or exchange: top holder of 2 different established tokens ($wif, bonk)"
 }
]
```

## UI check excerpt

- ok   board m_bd95541d260d: replay 16x reached the verdict in 18.9 s · STEP 28 OF 28 · top bar "RUN d96d0118ff · SEQ 28/28"
- ok   verdict m_bd95541d260d: exactly 4 why-lines from verdict.json
- ok   deep link /case/m_bd95541d260d/verdict: HTTP 200, renders on direct open and after hard refresh
- ok   deep link /memory: HTTP 200, renders on direct open and after hard refresh
- ok   deep link /case/m_bd95541d260d: HTTP 200, renders on direct open and after hard refresh
- ok   1440px: no console errors
