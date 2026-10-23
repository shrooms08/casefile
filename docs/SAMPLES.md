# Sample inputs and outputs

Three recorded investigations, copied from `demo_cases/` (generated from the files, nothing edited).
Input is a Solana token mint; output is the verdict JSON the Verdict agent wrote (`verdict.json`, key `verdict`).
Run any of them live with `uv run python scripts/investigate.py <mint>` or `POST /api/investigate {"mint": "<mint>"}`;
watch the recorded run at `https://casefile-ruddy-two.vercel.app/case/<case_id>`.

## 1. ヤギ

**Input** (mint): `FxzUDJHc9TbMJjGmthmnjbC9AF6FnGxNuFmbP1Jepump`

- Case id `m_bd95541d260d`, run `d96d0118ff`, recorded 2026-10-23 14:44:09 UTC
- RugCheck `rugged`: `false` · 13 agent calls · 380.3 s
- Trace: `demo_cases/m_bd95541d260d/trace.jsonl` (28 normalized events; raw original `runs/m_bd95541d260d/d96d0118ff/trace.jsonl`)
- Evidence the agents saw: `demo_cases/m_bd95541d260d/case_file.json` · receipts: `demo_cases/m_bd95541d260d/receipts.jsonl`
- Accepted claims cited by the why-lines, with their evidence: `demo_cases/m_bd95541d260d/verdict.json` → `accepted_claims`

**Output** (verdict):

```json
{
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
  {
   "claim_id": "D3",
   "sentence": "The only danger-level RugCheck risk is Low Liquidity at $282.56, indicating insufficient pool depth."
  }
 ],
 "what_would_change_my_mind": "Proof that insiders did not sell and the collapse resulted from a legitimate migration or market event rather than a rug.",
 "models_used": [
  "nvidia/nemotron-3.5-lightning-30b-a3b",
  "nvidia/nemotron-3.5-super-vl-120b-a12b"
 ]
}
```

## 2. kimchisol

**Input** (mint): `2LSQcdPsYvp1jqkth71xDPYRd7VcPYJX2972nj9spump`

- Case id `m_0c961a12701d`, run `7f8bc61d71`, recorded 2026-10-23 12:56:35 UTC
- RugCheck `rugged`: `false` · 22 agent calls · 321.2 s
- Trace: `demo_cases/m_0c961a12701d/trace.jsonl` (46 normalized events; raw original `runs/m_0c961a12701d/7f8bc61d71/trace.jsonl`)
- Evidence the agents saw: `demo_cases/m_0c961a12701d/case_file.json` · receipts: `demo_cases/m_0c961a12701d/receipts.jsonl`
- Accepted claims cited by the why-lines, with their evidence: `demo_cases/m_0c961a12701d/verdict.json` → `accepted_claims`

**Output** (verdict):

```json
{
 "label": "RUGGED",
 "one_line": "Price fell 93.54% with only thousands in liquidity and a danger-level low-liquidity risk, indicating a completed rug.",
 "why": [
  {
   "claim_id": "L1",
   "sentence": "A 93.54% price drop with $3,001.30 top-pair liquidity and $3,889.46 total liquidity shows inadequate depth."
  },
  {
   "claim_id": "D2",
   "sentence": "The only danger-level RugCheck risk is Low Liquidity at $616.71, reflecting collapsed FDV from tiny liquidity."
  },
  {
   "claim_id": "L3",
   "sentence": "A 561x volume-to-liquidity turnover shows depth cannot absorb sell pressure despite a near-balanced 0.99 buy-sell ratio."
  }
 ],
 "what_would_change_my_mind": "Proof that the price drop and low liquidity resulted from a legitimate migration or market event rather than a rug.",
 "models_used": [
  "nvidia/nemotron-3.5-lightning-30b-a3b",
  "nvidia/nemotron-3.5-super-vl-120b-a12b"
 ]
}
```

## 3. Bonk

**Input** (mint): `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`

- Case id `m_d54bf9a14eb4`, run `cca738afdd`, recorded 2026-10-23 12:44:47 UTC
- RugCheck `rugged`: `false` · 10 agent calls · 348.0 s
- Trace: `demo_cases/m_d54bf9a14eb4/trace.jsonl` (22 normalized events; raw original `runs/m_d54bf9a14eb4/cca738afdd/trace.jsonl`)
- Evidence the agents saw: `demo_cases/m_d54bf9a14eb4/case_file.json` · receipts: `demo_cases/m_d54bf9a14eb4/receipts.jsonl`
- Accepted claims cited by the why-lines, with their evidence: `demo_cases/m_d54bf9a14eb4/verdict.json` → `accepted_claims`

**Output** (verdict):

```json
{
 "label": "CAUTION",
 "one_line": "Only weak signal: mutable metadata; ample liquidity, no top-10 insiders, no mint/freeze authority.",
 "why": [
  {
   "claim_id": "L1",
   "sentence": "The token's $1.27M liquidity and $321k top pair give modest depth; 0.36% worst price change and 1.0 volume-to-liquidity show sufficient depth."
  },
  {
   "claim_id": "L2",
   "sentence": "The 0.0012 liquidity-to-FDV ratio reflects the ~$279M FDV and $1.27M liquidity, expected for an established multi-year token rather than insufficient depth."
  },
  {
   "claim_id": "H1",
   "sentence": "No top-10 holder is among the 48 graph-detected insiders; insider networks hold 33% of supply but zero are flagged, so top-10 concentration is unrelated."
  },
  {
   "claim_id": "H2",
   "sentence": "Excluding pools, lockers, and custodians, top-10 holders still hold 38.4% of supply, consistent with long-term holders or airdrop recipients given the 1,403-day age and no flagged insiders."
  },
  {
   "claim_id": "D1",
   "sentence": "The creator's retained update authority and true metadata_mutable flag mean metadata can be altered, a metadata risk despite null mint and freeze authorities."
  },
  {
   "claim_id": "D2",
   "sentence": "The creator's 14.6B token balance does not itself raise metadata risk; the retained update authority is the enabling factor."
  }
 ],
 "what_would_change_my_mind": "Evidence of liquidity being drained, price collapsing about 90% or more, or creator/insider control of top-10 holders.",
 "models_used": [
  "nvidia/nemotron-3.5-lightning-30b-a3b",
  "nvidia/nemotron-3.5-super-vl-120b-a12b"
 ]
}
```
