# Sponsor technology in Casefile

Every number here comes from a file in this repo; the file is named next to it.

## Zetaris: the data layer

**What it does.** Zetaris is the only thing that talks to the data sources. Python never calls
RugCheck or DexScreener itself; it sends Lightning SQL to Zetaris (`casefile/zetaris.py`, one
statement per request, all calls in a process serialized behind `ZETARIS_LOCK`).

1. **REST tables created at runtime, per token** (`casefile/sources.py`, `open_case`):
   `CREATE LIGHTNING REST TABLE <case_id>_dex FROM DEXSCREENER_REST` (DexScreener token endpoint) and
   `<case_id>_rug FROM RUGCHECK_REST` (RugCheck token report, about 2.5 MB for BONK). The `RUGCHECK_REST`
   database is created on first use; nothing existing is dropped or replaced.
2. **Flattened SchemaStore views** in container `casefile`: `pairs`, `summary`, `holders`, `risks`,
   `insiders`, `markets`, `known_accounts`, `lockers`. Zetaris infers a REST table's schema from each live
   response, so every nested field is parsed with `from_json(to_json(named_struct(...)), '<explicit schema>')`;
   a field that is null or missing for one token (WIF has `creator: null`, `risks: []`) cannot break the view.
   Field-by-field map: `fixtures/SOURCES.md`.
3. **Parquet evidence snapshots** (`casefile/snapshot.py`): each view is frozen once with
   `RUN EXPORT TO STORAGE (query = 'SELECT *, current_timestamp() AS captured_at FROM casefile.<view>', format = 'parquet', ...)`
   into Zetaris' local file storage and registered as `CREATE LIGHTNING FILESTORE TABLE <case_id>_<view>_snap FROM CASEFILE_SNAP`.
   Top holders are also frozen joined to RugCheck's known accounts and lockers (`<case_id>_holders_labelled_snap`),
   which is where labels such as "Pump Fun AMM" and "Creator" come from.
4. **One-query reads.** `casefile/case_file.py` reads all snapshot tables in a single `UNION ALL` query.
   Measured (`fixtures/SOURCES.md`): a live read of the views took 80.6 s (BONK) and 36.2 s (WIF); reads from
   the snapshots take 0.8 to 1.1 s (BONK) and 0.6 s (WIF).
5. **Agents read only the snapshots.** Each investigator gets slices of the snapshot tables in its prompt (from the one-query read above). For more it can call `query_case` (`casefile/agents/tools.py`), which accepts one SELECT, rejects
   write/DDL keywords, and only allows this case's `CASEFILE_SNAP` tables; it goes through the same lock and
   is logged to the trace. No demo run used `query_case`: the investigators answered from the slices. Each claim's evidence (`table · field · value`) is checked against the snapshot
   rows in code (`casefile/agents/evidence.py`) before the Skeptic reviews it.

Lessons recorded in `fixtures/SOURCES.md`: eight parallel exports wedged the local driver (exports now run one at a
time), two views over the same REST table cannot be joined in one query (labels are joined on the snapshots),
and `to_json(struct(*))` drops null fields unless `ignoreNullFields` is false.

## Meterless Engine implemented: H-MEM

**Files.** `casefile/hmem/*.ts` is the Meterless H-MEM reference implementation (Apache-2.0, `casefile/hmem/LICENSE`),
adapted with attribution headers; Casefile's changes are marked `Casefile:` (explicit entities on `add`, and
rule-derived dream proposals). `casefile/hmem/casefile.ts` is Casefile's wallet memory on top of it,
`casefile/hmem/cli.ts` the JSON bridge, `casefile/memory.py` the Python side (one call per phase, file lock),
`casefile/memory_summary.py` the read-only summary for the UI.

**What it stores.** After each verdict, one long-term factual record per (wallet, case, role) for the creator,
insider-flagged holders and the top-20 holders: token, mint, rank and share, label, whether the token is
established (pair older than 180 days and over 100,000 holders), and the verdict label. At the start of a case the
same records are written with verdict `PENDING`, so the derivation below can already combine this case with earlier ones.

**What it recalls.** At the start of every investigation, everything known about the creator and the top-20 holders
(exact `wallet:<address>` tag match, ranked with H-MEM's own scoring, each read logged in the trust ledger). Facts
the same case wrote on an earlier run are skipped. Recalled facts enter the case as evidence with table `H-MEM`.

**Derived memory.** A wallet that is a top holder in two or more different established tokens gets a
"likely custodian or exchange" record. It is created through H-MEM's dreaming approval boundary
(`proposeRule` then `approve`, ledger actions `dream_proposed` and `dream_approved`) with `derivedFrom` lineage.
The Skeptic must reject claims that treat such a wallet as an insider or owner (`casefile/agents/prompts.py`, rule 3).

**State in the demo snapshot** (`demo_cases/_memory.json`): 74 records, 59 wallets, 7 wallets seen in 2 or more
cases, 7 likely custodians.

**Tests.**
- Conformance (Meterless suite, `engines/hmem/conformance/runner.ts` at Meterless commit `1742dec`):
  `HMEM_IMPL=<repo>/casefile/hmem/index.ts npx --yes tsx conformance/runner.ts` → **13/13 checks passed**
  (record validation, feedback deltas, ranking order, sleep guardrails, conflict gate, ledger audit, dream boundary).
- Integration: `CASEFILE_LIVE_TESTS=1 uv run pytest tests/test_hmem.py`. In fresh processes with an empty memory
  folder it investigates BONK, then WIF, and asserts WIF recalls BONK's facts for the shared top holders
  `51yZyDSnec4xnUv7XLRVYcDyV4x3wUtzrDcRaYbmQU5j` and `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`, both marked
  likely custodian. Result: `docs/TEST_RESULTS.md`. The same recall is visible in the WIF demo trace
  (`demo_cases/m_d2f031d73387/trace.jsonl`, event `memory_recalled`, `custodian_wallets`).

## Meterless Nightshift: the AI provider

**Contract.** `casefile/llm.py` implements the Meterless Power Prompt (Runtime 1.4, provider contract v4): base URL
normalisation to `<host>/v1`, `Authorization: Bearer <token>` on every call (`rt-local` rejected), `meterless-app`
on every request and `meterless-scope: user` on chat, status from `GET /v1/models` (401/403 unauthorized, 200 with
`meterless/*` ids online), auto-detect on ports 8088, 8090, 8787 and 11434, a 180 s timeout, and connect links.
`scripts/check_nightshift.py` checks the done criteria: a wrong token shows unauthorized, Auto Detect finds the
runtime, and a plain text request on `meterless/auto` returns a string.

**Two apps, two lanes.** Nightshift binds routing per `meterless-app` id, so `role="fast"` sends `casefile-fast` and
`role="deep"` sends `casefile-deep`. In Nightshift each app's lane allowlist holds one cloud lane
(`lightning-fast`: Nemotron 3.5 Lightning, `super-deep`: Nemotron 3.5 Super); setup steps in `fixtures/PERF.md`.
The receipts keep `requested_mode: meterless/auto`; which model actually answered is recorded in `routed_model` and `winning_route`. The allowlist sets where a call starts, not every model that can finish it: in the WIF demo run Nightshift's consensus escalation re-ran one `casefile-fast` deployer call on Super (next section).

**Streaming.** Calls stream (SSE) with `meterless-trace: on`, so the final chunk carries the full receipt. Without
streaming, Nightshift's 45 s provider-header deadline (`CLOUD_FETCH_DEADLINE_MS`) aborted every call that needed
longer (`fixtures/PERF.md`).

**Receipts.** Every call's full Meterless receipt is appended to `runs/<case_id>/<run_id>/receipts.jsonl`; the
normalized trace gives each plan, claim, Skeptic decision and verdict the receipt id and model of the call that
produced it, and the case board shows them on every step. The four demo runs hold 50 receipts
(`demo_cases/*/receipts.jsonl`): 42 generated by Nemotron, 8 served from Nightshift's cache (6 exact, 2 semantic).

## NVIDIA Nemotron

| Role | Model (receipt `routed_model`) | Nightshift app |
|---|---|---|
| Investigators: holders, liquidity, deployer | sent to the fast lane: `nvidia/nemotron-3.5-lightning-30b-a3b` (Nemotron 3.5 Lightning 30B A3B) | `casefile-fast` |
| Planner, Skeptic, verdict | sent to the deep lane: `nvidia/nemotron-3.5-super-vl-120b-a12b` (Nemotron 3.5 Super VL 120B A12B) | `casefile-deep` |

`routed_model` in each receipt records which model actually answered. Across the 50 demo receipts: 28 `casefile-deep` calls answered by Super, 21 `casefile-fast` calls answered by Lightning, and 1 `casefile-fast` call answered by Super. That one is the WIF deployer investigator (claims D1 and D2, `demo_cases/m_d2f031d73387/trace.jsonl`): receipt `rcpt_req_oz1pxls2` shows a `final_synthesis` phase on Lightning (39,871 ms, coherence 0.39), then a `consensus_escalation` phase on Super (11,207 ms), with `routing.escalated_on_divergence: true` and Super as `winning_route`. Nightshift escalated the low-coherence answer; Casefile did not ask for Super.

All four demo runs list both models in `models_used` (`demo_cases/*/meta.json`). Where to see it: on the case board,
every claim shows `CLAIM <id> · <receipt id>` and the model that answered, the plan shows `PLANNER · NEMOTRON 3.5 SUPER` and its
receipt, and every Skeptic log line shows model and receipt.

Measured on the same small prompt (`fixtures/PERF.md`): Lightning used a median of 1,299 completion tokens in
about 20 s (the visible answer is about 50 tokens; the rest is reasoning Nightshift always enables); Super used 527
tokens in 14.8 s.

Receipt excerpts (redacted to routing, usage and status fields; the receipts hold no credentials):

Lightning, holders investigator reworking a rejected claim, ヤギ:

```json
{
 "file": "demo_cases/m_bd95541d260d/receipts.jsonl",
 "at": "2026-10-23T14:44:35.874+00:00",
 "case_id": "m_bd95541d260d",
 "run_id": "d96d0118ff",
 "app": "casefile-fast",
 "role": "fast",
 "requested_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
 "routed_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
 "receipt_id": "rcpt_req_qijay3dj",
 "latency_ms": 14688,
 "tokens": {
  "prompt_tokens": 2289,
  "completion_tokens": 941,
  "total_tokens": 3230
 },
 "response.meterless": {
  "schema": "meterless.compute_receipt.v1",
  "receipt_id": "rcpt_req_qijay3dj",
  "app": "casefile-fast",
  "requested_mode": "meterless/auto",
  "routed_model": "nvidia/nemotron-3.5-lightning-30b-a3b",
  "winning_route": {
   "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
   "label": "Nemotron 3.5 Lightning 30B A3B",
   "provider": "nvidia",
   "kind": "cloud",
   "tier": "A"
  },
  "phases": [
   {
    "phase": "tool_call_format",
    "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "ms": 14660,
    "tokensIn": 2289,
    "tokensOut": 941
   }
  ],
  "cache": {
   "status": "miss"
  },
  "cross_check": {
   "status": "skipped"
  },
  "privacy": {
   "path": "cloud-ok"
  },
  "cost": {
   "actual_usd": 0
  }
 },
 "first_message_starts": "You are the holders investigator. Claim ids start with H. Th…"
}
```

Super, Skeptic reviewing claims, ヤギ:

```json
{
 "file": "demo_cases/m_bd95541d260d/receipts.jsonl",
 "at": "2026-10-23T14:44:11.230+00:00",
 "case_id": "m_bd95541d260d",
 "run_id": "d96d0118ff",
 "app": "casefile-deep",
 "role": "deep",
 "requested_model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
 "routed_model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
 "receipt_id": "rcpt_req_qernre93",
 "latency_ms": 24634,
 "tokens": {
  "prompt_tokens": 1759,
  "completion_tokens": 1701,
  "total_tokens": 3460
 },
 "response.meterless": {
  "schema": "meterless.compute_receipt.v1",
  "receipt_id": "rcpt_req_qernre93",
  "app": "casefile-deep",
  "requested_mode": "meterless/auto",
  "routed_model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
  "winning_route": {
   "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
   "label": "Nemotron 3.5 Super VL 120B A12B",
   "provider": "nvidia",
   "kind": "cloud",
   "tier": "C"
  },
  "phases": [
   {
    "phase": "tool_call_format",
    "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "ms": 24584,
    "tokensIn": 1759,
    "tokensOut": 1701
   }
  ],
  "cache": {
   "status": "miss"
  },
  "cross_check": {
   "status": "skipped"
  },
  "privacy": {
   "path": "cloud-ok"
  },
  "cost": {
   "actual_usd": 0
  }
 },
 "first_message_starts": "You are the skeptic reviewing investigators' claims about a …"
}
```

## What was unique

- **Evidence frozen inside the data platform.** Zetaris fetches, shapes and freezes the evidence (REST tables → views
  → Parquet snapshots via `RUN EXPORT TO STORAGE`). Every claim cites its evidence as `table · field · value` (a snapshot field, a field computed from the snapshot, or an H-MEM fact), and code checks it before the Skeptic sees it, and the frozen case replays anywhere with no stack.
- **Memory as cross-case wallet reputation.** H-MEM is used to remember wallets across investigations. The derived
  "likely custodian or exchange" memory is created through H-MEM's dreaming approval boundary, and the Skeptic must
  respect it, so a known exchange wallet in WIF is not mistaken for an insider because it was already seen in BONK.
- **The receipt is the reasoning trace.** Each role is a separate Nightshift app bound to its own Nemotron lane. Every plan, claim, Skeptic decision and verdict carries the Meterless receipt id and `routed_model` of the call that produced it, so the trace shows which model actually answered, and the UI renders them.
