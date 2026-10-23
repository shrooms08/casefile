# Casefile test cases: 5 dumped Solana tokens

Snapshot taken **2026-10-23, about 02:45–03:10 UTC**. All values below come from the live APIs at that time.
They are observations from a dated snapshot, not verdicts. Live values will drift, and pump tokens can vanish.

## How they were found

1. **Candidates.** `GET https://api.rugcheck.xyz/v1/stats/rugs/ticker?limit=50` lists RugCheck's live rug events (`ruggedAt`, `peakMarketCapUSD`, `liquidityPulledUSD`). `GET /v1/stats/recent?window=1w&limit=100` lists the most-viewed tokens of the week. Both endpoints are public and appear in `https://api.rugcheck.xyz/swagger/doc.json`.
2. **Price check.** Candidates were batch-checked with `GET https://api.dexscreener.com/tokens/v1/solana/{up to 30 mints, comma-separated}`. I kept tokens with priceChange h24 or h6 of -90% or worse, or with a pool drained to near $0.
3. **Report check.** I pulled `GET /v1/tokens/{mint}/report` for 25 candidates (about 1 s between calls; 24 returned reports). The 5 below have a non-null creator, at least one `danger` risk, insider networks, and `graphInsidersDetected > 0`. Their DexScreener rows were then re-pulled with `GET /latest/dex/tokens/{mint}`, which is the endpoint Casefile uses.

## What the data shows across all candidates

- **`rugged` was `false` for every report I fetched (24 of 24).** This includes tokens on RugCheck's own rug ticker. In practice the danger risk, the insider graph and the DexScreener collapse carry the evidence, not `rugged`.
- **`topHolders[].insider` was never `true`.** Insider evidence only shows up in `graphInsidersDetected` and `insiderNetworks`.
- **The top holder at 78–99% is the pool itself.** For pump.fun tokens it is the Pump Fun AMM vault (`knownAccounts` labels it `type: AMM`). Raw top-10 % is therefore misleading, so "top-10 excl. AMM" is given too. That is a good reason to expose `knownAccounts`.
- **`lpLockedPct` is 100 on pump.fun AMM pools.** The LP is burned there, so these are dumps that drained the SOL side (sells into the pool), not LP withdrawals.
- **Fields that were the same for all 5:** mint and freeze authority `null`, metadata immutable, `creatorBalance` 0, risk list = `Low Liquidity` (danger) only.

---

## 1. ヤギ "Nagi and Pokke" — strongest case
`FxzUDJHc9TbMJjGmthmnjbC9AF6FnGxNuFmbP1Jepump`

**Why it qualifies:** it has the largest insider graph seen (874 insider wallets in 10 networks), a -97.7% day on $1.77M volume, and only $284 of SOL left in the pool.

| Field | Value |
|---|---|
| rugged / score / score_normalised | false / 2717 / 32 |
| risks | Low Liquidity — danger — `$283.52` |
| creator | `7RuGitVFXYZQ3Q3QEVSs14Jggv6a9Ky8AEthBENPqrCd` |
| graphInsidersDetected | **874** |
| insiderNetworks | **10**, largest `knotty-brick-bat` size 471 (tokenAmount ≈ 69.4% of supply), next size 335 |
| top-10 holders | 99.99% (99.75% Pump Fun AMM); excl. AMM 0.25%; totalHolders 165 |
| main market | pump_fun_amm `9XQyVNcE…Fw6NK`, lpLockedPct 100, quoteUSD $283.52 |
| DexScreener (pumpswap) | liquidity.usd $2,397 · fdv $2,119 · h24 **-97.72%** (h6 n/a) · vol24 $1,773,404 · txns24 14,083 buys / 8,847 sells |
| pairCreatedAt | 1792646197000 (2026-10-22 05:16 UTC); detectedAt 2026-10-22 05:16 |

## 2. kimchisol
`2LSQcdPsYvp1jqkth71xDPYRd7VcPYJX2972nj9spump`

**Why it qualifies:** it is on RugCheck's rug ticker (peak market cap $807k, $63.5k liquidity pulled, 48 minutes after launch). It also has insider networks, 3,017 holders and a -93% hour.

| Field | Value |
|---|---|
| rugged / score / score_normalised | false / 2506 / 31 |
| risks | Low Liquidity — danger — `$494.43` |
| creator | `DjK5yGvgsCuBnVPnWvf4Rh5T4FFYk8dbRQ823tzs4QGc` |
| graphInsidersDetected | 23 |
| insiderNetworks | 2, largest `peaceful-coffee-lion` size 17 |
| top-10 holders | 97.25% (91.25% Pump Fun AMM); excl. AMM 6.12%; totalHolders 3,017 |
| main market | pump_fun_amm `7c6siqtQ…5fGd`, lpLockedPct 100, quoteUSD $488; 2 meteoraDlmm pools at lpLockedPct 0 (~$3 each) |
| RugCheck rug ticker | ruggedAt 1792722932 (2026-10-23 02:35 UTC), timeToRugMinutes 48, peakMarketCapUSD 807,174, liquidityPulledUSD 63,466 |
| DexScreener (pumpswap, 1 of 4 pairs) | liquidity.usd $3,101 · fdv $2,872 · h24 **-93.28%** · h6 -93.28% · vol24 $1,684,305 · txns24 7,110 buys / 7,146 sells |
| pairCreatedAt | 1792720245000 (2026-10-23 01:50 UTC) |

## 3. ‮TOOP "‮nioctooP"
`6rnmvAAjieoG6ma82bP5jHdny5LAMr8uA8MRsBspfb28`

**Why it qualifies:** the pool is drained to $1.47 and fdv is $1 (-100%). RugCheck's ticker logged the rug 4 minutes after launch. A single network holds all 89 insider wallets. The name and symbol start with a U+202E right-to-left override character, so they render as "POOT"/"Pootcoin" spelled backwards.

| Field | Value |
|---|---|
| rugged / score / score_normalised | false / 3000 / 34 |
| risks | Low Liquidity — danger — `$0.78` |
| creator | `CUCrhzqpLsYsRfdTGL3W2Fngzrh9LKniqgZR2oZ17ETr` |
| graphInsidersDetected | **89** |
| insiderNetworks | 1, `clean-rose-leech` size 89 |
| top-10 holders | 100% (top holder `HLnpSz9h…TLcC` 91.33%, not labelled); totalHolders 21 |
| main market | meteora_damm_v2 `2RMpKbJL…f4Y2`, lpLockedPct 100, quoteUSD $0.78; totalMarketLiquidity $1.58 |
| RugCheck rug ticker | ruggedAt 1792723399 (2026-10-23 02:43 UTC), timeToRugMinutes 4, peakMarketCapUSD 186,193, liquidityPulledUSD 1,496 |
| DexScreener (meteora DAMM v2) | liquidity.usd **$1.47** · fdv **$1** · h24 / h6 / h1 **-100%** · vol24 $504 |
| pairCreatedAt | 1792723331000 (2026-10-23 02:42 UTC). A stale meteoradbc pair still shows fdv $155,930 with liquidity null. |

## 4. BO "Black October"
`E3MbXgxn8UsuRXBJPQfZZNPD1wksmQBhJdZdynNDZAS4`

**Why it qualifies:** it fell -92.9% on $633k volume and was still bleeding (-37% over 6 h). It has 3 insider networks and 1,865 holders.

| Field | Value |
|---|---|
| rugged / score / score_normalised | false / 2344 / 31 |
| risks | Low Liquidity — danger — `$656.49` |
| creator | `CgymPsTbFDoUXUk8NuS5ihogc7ar9bTbKT5grBSJBJpG` |
| graphInsidersDetected | 20 |
| insiderNetworks | 3, largest `innocent-sunset-gorilla` size 11 (tokenAmount ≈ 40.6% of supply) |
| top-10 holders | 92.41% (81.85% Pump Fun AMM); excl. AMM 11.23%; totalHolders 1,865 |
| main market | pump_fun_amm `9qEUbbCu…evaCd`, lpLockedPct 100, quoteUSD $656 |
| DexScreener (pumpswap) | liquidity.usd $3,111 · fdv $3,001 · h24 **-92.87%** · h6 -37.04% · vol24 $633,105 · txns24 8,128 buys / 6,896 sells |
| pairCreatedAt | 1792640805000 (2026-10-22 03:46 UTC) |

## 5. DARK "DARKFUND"
`DarKbNHeW6yHtPv425gH5odvVYMxXb2ZbhyRX3PtfUND`

**Why it qualifies:** it fell -93.8% in a day and -38% over 6 h. It has an insider network. Its two side pools on Meteora are unlocked (lpLockedPct 0) and drained to under $2. Its main pair is quoted in XMR, another pump token, rather than SOL.

| Field | Value |
|---|---|
| rugged / score / score_normalised | false / 2447 / 31 |
| risks | Low Liquidity — danger — `$553.57` |
| creator | `7n9gSoiXCjdfEguCYTsC8ZbN9Yei6AzVBCvbmcssCzBQ` |
| graphInsidersDetected | 5 |
| insiderNetworks | 1, `smooth-red-woodpecker` size 5 |
| top-10 holders | 91.43% (78.24% Pump Fun AMM); excl. AMM 13.97%; totalHolders 933 |
| main market | pump_fun_amm `DJc3cHgv…ZmLm`, lpLockedPct 100, quoteUSD $553; 2 meteora_damm_v2 pools at lpLockedPct 0 ($0.88 and $0.13) |
| DexScreener (pumpswap vs XMR) | liquidity.usd $2,595 · fdv $2,614 · h24 **-93.81%** · h6 -38.31% · vol24 $97,154 · Meteora pairs liq $1.49 / $0.12 |
| pairCreatedAt | 1792670450000 (2026-10-22 12:00 UTC) |

---

**Alternate (no insider data):** Claude AI `iMjheLWDgyCzUaEbfNT83xBVXBxQyPKeMXZX9Hvpump` was the biggest rug on the ticker (peak $1.93M, $57.8k pulled, 56 minutes after launch), with DexScreener h1 -99.52%. It has a creator and a danger risk, but `graphInsidersDetected` is 0 and `insiderNetworks` is empty. It is useful as a "dump without an insider graph" case.
