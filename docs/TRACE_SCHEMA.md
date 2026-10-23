# Casefile trace schema (v1)

The UI reads investigations as a list of **normalized trace events**. The agents write raw events to
`runs/<case_id>/<run_id>/trace.jsonl`; `casefile/trace_schema.py` turns them into this schema. The same
events come from `GET /api/cases/{case_id}/trace`, the replay SSE and the live SSE.

## Event

| Field | Type | Meaning |
|---|---|---|
| `seq` | int | 1, 2, 3... within the run, no gaps |
| `ts` | ISO 8601 string | when it happened (UTC) |
| `run_id` | string | one investigation |
| `case_id` | string | `m_` + sha1(mint)[:12] |
| `type` | string | one of the 13 types below |
| `agent` | string | `casefile`, `h-mem`, `planner`, `holders`, `liquidity`, `deployer`, `skeptic`, `verdict` |
| `model` | string or null | routed model for LLM steps (e.g. `nvidia/nemotron-3.5-super-vl-120b-a12b`) |
| `receipt_id` | string or null | Meterless receipt for that LLM call |
| `title` | string | one short human-readable line |
| `detail` | object | type-specific fields (below) |

Normalization is prefix-stable: events for the first N raw lines never change when more lines arrive.

## SSE

`/replay` and `/stream` send one message per event: `id: <seq>` and `data: <event JSON>`. The last
message is `data: {"type": "done", "case_id", "run_id", "summary": {...}}`, which is not a trace event.
For a finished run the message before `done` is the `verdict` (or an `error` if the run stopped).
Replay keeps the recorded gaps divided by `speed` (1, 4 or 16), with any single gap capped at 2.5 s.
Lines starting with `:` are keep-alive comments.

## Types

### `case_opened`

The run starts: the case file was read from the frozen CASEFILE_SNAP snapshot tables.

```json
{
 "seq": 1,
 "ts": "2026-10-23T14:44:09.867+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "case_opened",
 "agent": "casefile",
 "model": null,
 "receipt_id": null,
 "title": "Opened ヤギ from 6 frozen Zetaris snapshot tables",
 "detail": {
  "mint": "FxzUDJHc9TbMJjGmthmnjbC9AF6FnGxNuFmbP1Jepump",
  "symbol": "ヤギ",
  "snapshot_tables": {
   "summary": "casefile_snap.m_bd95541d260d_summary_snap",
   "pairs": "casefile_snap.m_bd95541d260d_pairs_snap",
   "markets": "casefile_snap.m_bd95541d260d_markets_snap",
   "risks": "casefile_snap.m_bd95541d260d_risks_snap",
   "insiders": "casefile_snap.m_bd95541d260d_insiders_snap",
   "holders": "casefile_snap.m_bd95541d260d_holders_labelled_snap"
  }
 }
}
```

### `memory_recalled`

H-MEM recall for the creator and top-20 holders. `facts` are prior-case facts and derived notes; `custodian_wallets` lists wallets H-MEM marks likely custodian or exchange; `observed_this_case` is what was written for this case before recall (verdict PENDING).

```json
{
 "seq": 2,
 "ts": "2026-10-23T14:44:10.449+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "memory_recalled",
 "agent": "h-mem",
 "model": null,
 "receipt_id": null,
 "title": "H-MEM recalled 0 fact(s) for 0 of 5 wallets",
 "detail": {
  "wallets_asked": 5,
  "wallets_with_memory": 0,
  "facts": [],
  "custodian_wallets": [],
  "observed_this_case": {
   "created": 0,
   "updated": 5,
   "unchanged": 0,
   "derived": 0,
   "derived_ids": [],
   "established": false
  },
  "seconds": 0.17
 }
}
```

### `plan`

The planner (deep model) wrote its questions. `computed` holds the arithmetic fields it saw.

```json
{
 "seq": 3,
 "ts": "2026-10-23T14:44:10.858+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "plan",
 "agent": "planner",
 "model": "nvidia/nemotron-3.5-super-vl-120b-a12b",
 "receipt_id": "rcpt_req_59q1rbo9",
 "title": "Planner wrote 4 questions",
 "detail": {
  "questions": [
   {
    "id": "q1",
    "investigator": "liquidity",
    "question": "Is $2,397.32 the total remaining liquidity across both pairs, and what absolute USD amount is left?"
   },
   {
    "id": "q2",
    "investigator": "holders",
    "question": "Do the 874 detected graph insiders control 85.52% of supply, with the largest network at 69.43%?"
   },
   {
    "id": "q3",
    "investigator": "deployer",
    "question": "With creator balance 0.0 and authorities null, does retained system-program update authority pose metadata risk if metadata_mutable=false?"
   },
   "…"
  ],
  "computed": {
   "worst_price_change_pct": -97.72,
   "own_liquidity_usd": 2397.32,
   "top_pair_liquidity_usd": 2397.32,
   "top_pair_fdv_usd": 2119.0,
   "volume_to_liquidity_24h": 739.7,
   "insider_networks_supply_pct": 85.52,
   "largest_insider_network_supply_pct": 69.43,
   "danger_risks": [
    "Low Liquidity"
   ],
   "pair_age_days": 1.4,
   "established": false,
   "top10_pct_all": 99.99,
   "top10_pct_excluding_pools_lockers": 0.25,
   "top10_pct_excluding_pools_lockers_custodians": 0.25,
   "insider_flagged_holders": 0,
   "buy_sell_ratio_24h": 1.59,
   "liquidity_to_fdv": 1.1313,
   "own_pair_count": 2
  }
 }
}
```

### `investigator_started`

One per investigator (holders, liquidity, deployer), with its questions. For runs recorded before agent versions existed this is derived from the plan (`detail.synthesized: true`).

```json
{
 "seq": 4,
 "ts": "2026-10-23T14:44:10.859+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "investigator_started",
 "agent": "holders",
 "model": null,
 "receipt_id": null,
 "title": "Holders investigator starts on 1 question(s)",
 "detail": {
  "questions": [
   {
    "id": "q2",
    "investigator": "holders",
    "question": "Do the 874 detected graph insiders control 85.52% of supply, with the largest network at 69.43%?"
   }
  ]
 }
}
```

### `sql_query`

An investigator used `query_case` (read-only SELECT on this case's snapshot tables). `ok: false` means the query was refused or failed (`error`). No recorded demo run has one yet, so the example shape below is labelled `example_only`.

```json
{
 "seq": 1,
 "ts": "2026-10-23T14:46:02.120+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "sql_query",
 "agent": "holders",
 "model": null,
 "receipt_id": null,
 "title": "holders ran query_case: 3 rows",
 "detail": {
  "sql": "SELECT owner, pct, label FROM casefile_snap.m_bd95541d260d_holders_labelled_snap WHERE label IS NULL ORDER BY pct DESC",
  "ok": true,
  "rows": 3,
  "sample": [
   {
    "owner": "9UnZnrFJ1CXCmCorgGU9NvYkX5np1h4v4ympx3Nrdw3v",
    "pct": "0.2456",
    "label": null
   }
  ],
  "error": null,
  "example_only": true
 }
}
```

### `claim`

An investigator's claim, with its evidence. Each evidence item carries `verified` and `check` from the mechanical lookup against the snapshot data. A revised claim has `revision_of` (the earlier wording).

```json
{
 "seq": 7,
 "ts": "2026-10-23T14:44:11.229+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "claim",
 "agent": "holders",
 "model": null,
 "receipt_id": null,
 "title": "H1: The 874 detected graph insiders hold 85.52% of the token supply, with the largest network controlling 69.43%.",
 "detail": {
  "id": "H1",
  "claim": "The 874 detected graph insiders hold 85.52% of the token supply, with the largest network controlling 69.43%.",
  "confidence": "medium",
  "evidence": [
   {
    "table": "computed",
    "field": "insider_networks_supply_pct",
    "value": 85.52,
    "source_api_url": null,
    "formula": "100 * sum(insiders.token_amount) / summary.supply",
    "verified": true,
    "check": "computed insider_networks_supply_pct = 85.52"
   },
   {
    "table": "computed",
    "field": "largest_insider_network_supply_pct",
    "value": 69.43,
    "source_api_url": null,
    "formula": "100 * max(insiders.token_amount) / summary.supply",
    "verified": true,
    "check": "computed largest_insider_network_supply_pct = 69.43"
   }
  ],
  "evidence_verified": "2/2",
  "innocent_explanation_checked": "The high supply share stems from aggregated transfer networks rather than direct insider ownership of individual wallets.",
  "revision_of": null
 }
}
```

### `skeptic_decision`

The skeptic (deep model) accepts or rejects one claim. `round` is `review` or `re_review`.

```json
{
 "seq": 9,
 "ts": "2026-10-23T14:44:35.873+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "skeptic_decision",
 "agent": "skeptic",
 "model": null,
 "receipt_id": null,
 "title": "Skeptic rejects H1: '874 insiders' unverified, conflicts with total_holders=165; only supply pcts verified.",
 "detail": {
  "id": "H1",
  "decision": "reject",
  "reason": "'874 insiders' unverified, conflicts with total_holders=165; only supply pcts verified.",
  "fix_request": "Remove unsupported insider count or provide verified count; retain verified pct figures.",
  "round": "review"
 }
}
```

### `rework_requested`

Follows a first-round rejection: the claim goes back to its investigator once with `fix_request`.

```json
{
 "seq": 10,
 "ts": "2026-10-23T14:44:35.873+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "rework_requested",
 "agent": "skeptic",
 "model": null,
 "receipt_id": null,
 "title": "H1 sent back once: Remove unsupported insider count or provide verified count; retain verified pct figures.",
 "detail": {
  "id": "H1",
  "fix_request": "Remove unsupported insider count or provide verified count; retain verified pct figures."
 }
}
```

### `claim_dropped`

A claim that will not reach the verdict: withdrawn after rejection, still rejected after the one fix round, or never reviewed.

```json
{
 "seq": 39,
 "ts": "2026-10-23T12:58:58.393+00:00",
 "run_id": "7f8bc61d71",
 "case_id": "m_0c961a12701d",
 "type": "claim_dropped",
 "agent": "skeptic",
 "model": null,
 "receipt_id": null,
 "title": "L2 dropped: still rejected after one fix round",
 "detail": {
  "id": "L2",
  "why": "still rejected after one fix round",
  "claim": "The liquidity‑to‑FDV ratio of 1.087 exceeds 1 solely because FDV collapsed to $2,761, not because depth is sound; the token bears a danger‑level risk named '…",
  "reason": "liquidity_to_fdv and top_pair_fdv verified, but the risk evidence item is unverified risks value is 616.71 not Low Liquidity; cannot carry the danger-risk cl…"
 }
}
```

### `retry`

An LLM call failed (`kind: call failed`, e.g. Nightshift's 45 s abort or an NVIDIA 500) or returned invalid JSON (`kind: invalid output`) and is being retried.

```json
{
 "seq": 27,
 "ts": "2026-10-23T14:48:57.226+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "retry",
 "agent": "verdict",
 "model": null,
 "receipt_id": null,
 "title": "verdict verdict: call failed, retrying (attempt 1)",
 "detail": {
  "step": "verdict",
  "kind": "call failed",
  "attempt": 1,
  "error": "Meterless stream error: {\"error\": {\"message\": \"500: {\\\"message\\\":\\\"Failed to generate completions\\\",\\\"type\\\":\\\"Internal Server Error\\\",\\\"code\\\":500}\", \"type\"…"
 }
}
```

### `fallback`

A deep-model step kept timing out and gets one try on the fast model. No recorded demo run needed one yet, so the example below is labelled `example_only`.

```json
{
 "seq": 2,
 "ts": "2026-10-23T14:46:02.120+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "fallback",
 "agent": "verdict",
 "model": null,
 "receipt_id": null,
 "title": "verdict: deep model kept timing out, one try on the fast model",
 "detail": {
  "step": "verdict",
  "from": "deep",
  "to": "fast",
  "reason": "Meterless stream error: request_aborted",
  "example_only": true
 }
}
```

### `verdict`

The final verdict from accepted claims only. Every `why` item names an accepted `claim_id`.

```json
{
 "seq": 28,
 "ts": "2026-10-23T14:50:29.842+00:00",
 "run_id": "d96d0118ff",
 "case_id": "m_bd95541d260d",
 "type": "verdict",
 "agent": "verdict",
 "model": null,
 "receipt_id": null,
 "title": "Verdict RUGGED: Insiders control 85.52% of supply, price fell 97.72%, and only about $2.4k liquidity remains with a danger-level low-li…",
 "detail": {
  "label": "RUGGED",
  "one_line": "Insiders control 85.52% of supply, price fell 97.72%, and only about $2.4k liquidity remains with a danger-level low-liquidity risk, indicating a completed rug.",
  "why": [
   {
    "claim_id": "H1",
    "sentence": "Insider networks hold 85.52% of supply, with the largest network controlling 69.43%."
   },
   {
    "claim_id": "L1",
    "sentence": "Total remaining liquidity is only $2,397.32 across both pairs."
   },
   {
    "claim_id": "L2",
    "sentence": "The FDV collapsed to $2,119 after a 97.72% price drop, so liquidity exceeds FDV rather than showing healthy depth."
   },
   "…"
  ],
  "what_would_change_my_mind": "Proof that insiders did not sell and the collapse resulted from a legitimate migration or market event rather than a rug.",
  "models_used": [
   "nvidia/nemotron-3.5-lightning-30b-a3b",
   "nvidia/nemotron-3.5-super-vl-120b-a12b"
  ]
 }
}
```

### `error`

A step failed for good (e.g. an investigator whose skeptic review failed every retry) or the run stopped (`step: run_failed`).

```json
{
 "seq": 26,
 "ts": "2026-10-23T11:58:53.517+00:00",
 "run_id": "94b27a787e",
 "case_id": "m_0c961a12701d",
 "type": "error",
 "agent": "deployer",
 "model": null,
 "receipt_id": null,
 "title": "deployer: deployer investigate: Meterless stream error: {\"error\": {\"message\": \"The request was aborted before…",
 "detail": {
  "step": "investigator_failed",
  "error": "deployer investigate: Meterless stream error: {\"error\": {\"message\": \"The request was aborted before completion.\", \"type\": \"invalid_request_error\", \"code\": \"r…"
 }
}
```
