# Casefile performance notes (Day 2, 2026-10-23)

All numbers are from this Mac, through Nightshift (Meterless Runtime) to NVIDIA cloud models.
Raw receipts: `runs/_perf/receipts.jsonl` and `runs/<case_id>/receipts.jsonl` (gitignored).

## A1. Deep model routing

Nightshift binds each `meterless-app` id to a routing mode, and a bound app's requested model is
recorded but not obeyed (`bindAppMode` in `engine/proxy.js`). The only per-app model pin is the
app card's lane allowlist (`AppLanesMenu` in `apps.js`, enforced by `resolveAppLaneAllow` /
`modelOnAllowedLanes` in `engine/select.js`). It lists lanes, not catalog models, so both models
were first added as cloud lanes.

- `llm.py` now sends `meterless-app: casefile-fast` for role=fast and `casefile-deep` for role=deep.
- Nightshift UI: Engineer mode on; Lanes: cloud lanes `super-deep`
  (nvidia/nemotron-3.5-super-vl-120b-a12b) and `lightning-fast` (nvidia/nemotron-3.5-lightning-30b-a3b);
  Console > Apps: casefile-deep pressed `deep` + allowlist `super-deep`; casefile-fast pressed `fast` +
  allowlist `lightning-fast`.
- Verified with `scripts/check_nightshift.py`: fast -> nemotron-3.5-lightning-30b-a3b,
  deep -> nemotron-3.5-super-vl-120b-a12b (routed_model in the receipt). No fallback needed.

## A2. Thinking cost (fast role, same ~440-token prompt, one call at a time)

The prompt asks for `{"lines": [3 strings]}` from a small BONK evidence JSON, with a nonce so the
Nightshift exact-match cache cannot answer. 3-4 runs per variant (median shown).

| Variant | Runs | Median completion tokens | Median seconds | Notes |
|---|---|---|---|---|
| baseline | 4 | 1,299 | 20.1 | one run aborted at 45.1 s (HTTP 499) |
| (1) system `/no_think` | 4 | 1,626 | 18.2 | |
| (2) system `detailed thinking off` | 4 | 1,683 | 20.0 | |
| (3) body `chat_template_kwargs.enable_thinking=false` | 4 | 1,926 | 20.3 | silently dropped by Nightshift (see below) |
| (4) `max_tokens=800` + JSON mode | 1 | - | 9.6 | HTTP 502 `nemotron-3.5-lightning-30b-a3b_empty_response`: reasoning used the budget |
| (1)+(2)+(3) combined | 1 | 1,454 | 15.0 | |
| JSON mode only | 1 | 1,516 | 18.7 | |
| system `Think briefly...` | 2 | 1,403 | 15.8 | |
| deep (Super 120B) baseline | 1 | 527 | 14.8 | Super reasons far less on this prompt |
| deep + body (3) | 1 | - | - | HTTP 502 from NVIDIA: `Failed to generate completions` |

The visible answer is ~50 tokens; everything else is hidden reasoning. No variant moved the
median outside run-to-run noise, and none reached the < 10 s target.

Why, from Nightshift's code: `providers.js` `nvidiaThinkingBody()` always sends
`chat_template_kwargs.enable_thinking = req.reasoning ?? model.reasoning`, and the Nemotron 3.5
rows in `models.js` have `reasoning: true`. The client cannot set `req.reasoning`: the proxy only
passes through `PASSTHRU_KEYS` (`top_p, stop, seed, ...`) plus `reasoning_effort` / `verbosity`,
which the NVIDIA adapter ignores. So thinking cannot be switched off through Nightshift today, and
`/no_think` / `detailed thinking off` are Llama-Nemotron conventions the 3.5 models do not follow.

**Chosen setting:** no thinking switch (none works, and (3) breaks Super). The overridable knobs
`reasoning_effort`, `max_tokens` and `extra_body` stay on `llm.chat()` for later runtimes.
Agent prompts say "Think briefly" and ask for short outputs, which keeps calls mostly under 45 s.

### The 45 s abort, and the streaming fix

`providers.js` has `CLOUD_FETCH_DEADLINE_MS = 45_000` (time until the provider's response headers)
and `orchestrator.js` has `TTFB_TIMEOUT_CLOUD_MS = 45_000`. A non-streaming request only gets its
headers when the whole answer is done, so any call over 45 s died with HTTP 499
`request_aborted`. `llm.chat()` now streams by default (`stream=True`, header `meterless-trace: on`
so the final SSE chunk carries the full receipt). Calls of 55-80 s now complete; a call whose
first visible token comes after 45 s of hidden reasoning can still be cut, so agent steps retry
transient 499/502 errors up to twice.

## Investigations (final proof runs, cases already opened)

| Case | Verdict | Seconds | LLM calls | Aborted/failed calls |
|---|---|---|---|---|
| BONK | CAUTION | 609 | 17 | 8 |
| WIF | CAUTION | 439 | 17 | 3 |
| ヤギ | RUGGED | 330 | 16 | 6 |
| kimchisol | RUGGED | 326 | 22 | 6 |

Target was under 180 s; not met. A clean run (no aborts) takes about 210-280 s: planner ~40 s,
investigators ~40-60 s (concurrent), skeptic ~20-45 s per lane (pipelined), fix ~20 s, verdict
~20-45 s. Each aborted call costs ~45 s plus backoff, and 20-40% of calls were aborted. What
would close the gap: a Nightshift setting that turns Nemotron thinking off or raises the 45 s
first-token limit, or binding casefile-fast to a non-reasoning model.

Opening a new case (REST tables, views, sequential snapshot exports) is a one-time cost: kimchisol
took 66 s. Snapshot reads after that are ~1 s.
