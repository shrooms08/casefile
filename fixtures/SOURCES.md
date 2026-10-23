# Casefile data sources

Both sources are registered as Zetaris Lightning REST tables and flattened into
SchemaStore views in container `casefile`. Python never calls these APIs directly;
it only runs SQL against the views (`casefile/case_file.py`).

Per-token object names use `cid = "m_" + sha1(mint)[:12]` (mapping kept in `cases.json`).
Samples in this folder are trimmed copies of live BONK responses from 2026-10-23.

## DexScreener (`bonk_dexscreener.json`, trimmed to 3 of 30 pairs)

`GET https://api.dexscreener.com/latest/dex/tokens/{mint}` → `{schemaVersion, pairs: [...]}`

Zetaris: `DEXSCREENER_REST.<cid>_dex` → view `casefile.<cid>_pairs` (one row per pair).

| Field | Meaning | In view as |
|---|---|---|
| `chainId`, `dexId` | chain and DEX (orca, raydium, meteora...) | `chain`, `dex` |
| `pairAddress`, `url` | pool address, DexScreener link | `pair_address`, `url` |
| `baseToken.{address,symbol,name}` | the token side of the pool | `base_address`, `symbol`, `name` |
| `quoteToken.{address,symbol}` | SOL / USDC side | `quote_address`, `quote_symbol` |
| `priceUsd`, `priceNative` | **strings** in the JSON, cast to DOUBLE | `price_usd`, `price_native` |
| `liquidity.usd` (`.base`, `.quote`) | pool liquidity | `liquidity_usd` |
| `volume.{m5,h1,h6,h24}` | USD volume per window | `volume_m5` ... `volume_24h` |
| `priceChange.{m5,h1,h6,h24}` | % change per window | `price_change_m5` ... `price_change_24h` |
| `txns.{h1,h24}.{buys,sells}` | trade counts (m5, h6 also exist) | `buys_h1`, `sells_h1`, `buys_24h`, `sells_24h` |
| `fdv`, `marketCap` | valuation | `fdv`, `market_cap` |
| `pairCreatedAt` | epoch **ms** | `pair_created_at_ms` |

Not used yet: `labels`, `info.{imageUrl,websites,socials}`.
Note: the endpoint returns pairs where the token is base *or* quote; `case_file` prefers
pairs whose `base_address` is the mint. `pairs` is `null` for unknown tokens (handled).

## RugCheck (`bonk_rugcheck.json`, trimmed)

`GET https://api.rugcheck.xyz/v1/tokens/{mint}/report`. No key needed. The full BONK
report is 2.5 MB, mostly `markets` (1,283 pools) and `knownAccounts`. The fixture is
trimmed to 10 holders, 2 markets, 5 known accounts and 2 lockers.

Zetaris: `RUGCHECK_REST.<cid>_rug` → five views.

### `casefile.<cid>_summary` (one row)
| Field | In view as |
|---|---|
| `mint`, `tokenMeta.{symbol,name}` | `mint`, `symbol`, `name` |
| `creator`, `creatorBalance` | `creator`, `creator_balance` (creator is `null` for WIF) |
| `score`, `score_normalised` | `score` (raw, higher = riskier), `score_normalised` (1-10ish) |
| `rugged` | `rugged` |
| `totalHolders`, `totalLPProviders` | `total_holders`, `total_lp_providers` |
| `totalMarketLiquidity`, `totalStableLiquidity` | `total_market_liquidity`, `total_stable_liquidity` |
| `price` | `price` |
| `mintAuthority`, `freezeAuthority` | `mint_authority`, `freeze_authority` (null = renounced) |
| `tokenMeta.{mutable,updateAuthority}` | `metadata_mutable`, `update_authority` |
| `token.{supply,decimals}` | `supply`, `decimals` |
| `graphInsidersDetected` | `graph_insiders_detected` (count of insider wallets in the transfer graph) |
| `detectedAt`, `deployPlatform`, `launchpad.name` | `detected_at`, `deploy_platform`, `launchpad` |
| `transferFee.pct` | `transfer_fee_pct` |
| `verification.{jup_verified,jup_strict}` | `jup_verified`, `jup_strict` |
| `lockerScanStatus`, `tokenProgram` | `locker_scan_status`, `token_program` |

### `casefile.<cid>_holders` (top 20)
`topHolders[]`: `address` → `token_account`, `owner`, `pct`, `uiAmount` → `ui_amount`, `insider`.
(`amount`, `decimals`, `uiAmountString` exist but are redundant.)

### `casefile.<cid>_risks`
`risks[]`: `name`, `level` (`warn`/`danger`), `score`, `description`, `value`. Empty for WIF.

### `casefile.<cid>_insiders`
`insiderNetworks[]`: `id` → `network_id`, `type` (e.g. `transfer`), `size`, `activeAccounts`,
`tokenAmount`, `currentHolding`. This is RugCheck's clustering of linked wallets, which is
the strongest "coordinated dump" evidence available here.

### `casefile.<cid>_markets` (LP info)
`markets[]`: `pubkey` → `market`, `marketType`, `mintA`, `mintB`, and from `lp`:
`baseUSD`, `quoteUSD`, `lpLockedPct`, `lpLockedUSD`. Gives per-pool LP lock status.
`case_file` reads only the top 25 (by locked USD, then quote USD).

### Present but not exposed yet
- `knownAccounts`: an object keyed by wallet address (`{name, type}`: AMM, CEX...). Useful
  for labelling holders (e.g. "this 8% holder is an exchange"). It's a dynamic-key object,
  so it needs the `from_json(to_json(..), 'map<string,struct<..>>')` technique; not done yet.
- `lockers` (dynamic-key, `{type, unlockDate, usdcLocked, uri}`), `lockerOwners`.
- `markets[].lp.holders` (LP token holders per pool), `markets[].*Account` details.
- `events` (empty for BONK/WIF), `fileMeta`, `verification.description`, `validation`.
- `creatorTokens` (other tokens by the same creator; null for BONK/WIF).
- `/v1/tokens/{mint}/report/summary` is a much smaller endpoint (score, risks, `lpLockedPct`)
  if the full report ever becomes too slow.

## Zetaris notes / quirks found

- **Schema varies per token.** Zetaris infers the REST table schema from each live
  response. WIF has `creator: null` and `risks: []`, and unknown tokens have `pairs: null`.
  Plain `explode(risks)` + `r.name` would fail on those. Every view therefore parses
  through `from_json(to_json(named_struct('a', field)), '<explicit schema>')`, which
  tolerates null-typed and missing fields (they come back NULL). No view had to be
  simplified or dropped.
- **Speed.** A REST table refetches the API on every query. RugCheck views take about 10-20 s
  each (2.5 MB report). `case_file` runs the six view queries in parallel (about 25-35 s total).
  Each view is a separate fetch, so the views of one case file can be seconds apart.
  `CACHE TABLE` is a session cache and wasn't used.
- `SHOW TABLES IN casefile` lists SchemaStore views (`table_identifier`, uppercase), and
  `SHOW LIGHTNING TABLES <db>` lists REST tables. `open_case` checks both before creating
  anything and also treats "already exists" as success.
- All values come back from `/sql-editor/sqls/run` as strings; `case_file` converts known
  numeric/boolean columns.
