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

### `casefile.<cid>_known_accounts`
`knownAccounts` is an object keyed by address (`{name, type}`), parsed as
`map<string,struct<name,type>>` and exploded: `address`, `name`, `type` (AMM, CEX, LOCKER, CREATOR...).
BONK has 2,606 AMM + 14 LOCKER + 1 CREATOR entries; WIF 1,810 AMM + 8 LOCKER.

### `casefile.<cid>_lockers`
`lockers` (keyed by locker account): `locker`, `type` (jupiter_locker, raydium_locker...),
`program_id`, `token_account`, `owner`, `unlock_date` (epoch s), `usdc_locked`, `uri`.

### Holder labels
`case_file` adds `label` / `label_type` to top holders: knownAccounts matched on the holder's
`owner` wallet, then on its `token_account`, then lockers matched on `token_account` (label
`locker`). Unlabelled holders keep `label = NULL`. The join runs in Zetaris SQL on the snapshot
tables. It can't run on the live views: two views over the same REST table in one query fail
with `[MISSING_ATTRIBUTES.RESOLVED_ATTRIBUTE_APPEAR_IN_OPERATION] Resolved attribute(s)
"knownAccounts" missing from ...` (a Spark self-join problem), so `fresh=True` reads have no labels.

### Present but not exposed yet
- `lockerOwners`, `markets[].lp.holders` (LP token holders per pool), `markets[].*Account` details.
- `events` (empty for BONK/WIF), `fileMeta`, `verification.description`, `validation`.
- `creatorTokens` (other tokens by the same creator; null for BONK/WIF).
- `/v1/tokens/{mint}/report/summary` is a much smaller endpoint (score, risks, `lpLockedPct`).

## Evidence snapshots (approach used: Zetaris-managed Parquet tables)

`open_case` freezes each case view once, entirely inside Zetaris (`casefile/snapshot.py`):

1. `RUN EXPORT TO STORAGE (query = 'SELECT *, current_timestamp() AS captured_at FROM casefile.<cid>_<view>',
   path = 'file:///home/zetaris/customer-data/shared/casefile_snap/<cid>_<view>_snap/<UTC stamp>', format = 'parquet',
   saveMode = 'errorifexists', optionsBase64 = 'e30=')`. Zetaris runs the view (so it still fetches and
   shapes the data) and writes the result to its own local file storage
   (`ZETARIS_LOCAL_FILE_SYTEM_ROOT_PATH` in the driver container).
2. `CREATE LIGHTNING FILESTORE TABLE <cid>_<view>_snap FROM CASEFILE_SNAP FORMAT PARQUET OPTIONS (PATH "<same path>")`
   in a new Lightning database `CASEFILE_SNAP`.

`case_file` then reads `casefile_snap.<cid>_<view>_snap`. Each row has `captured_at` (Zetaris
clock), and `cases.json` records, per view, the snapshot table, the Parquet path, the source
view and the exact SQL that produced it. Nothing is overwritten (`errorifexists`, and existing
snapshot tables are kept); each export goes to a new timestamped folder
`.../casefile_snap/<cid>_<view>_snap/<UTC stamp>`. `get_case_file(mint, fresh=True)` skips the snapshots and reads the live views.

Why this and not the alternatives in the docs: there is no plain CTAS into a Lightning database,
there are no JDBC datasources on this instance (`SHOW DATASOURCES` is empty), `MATERIALIZE USL TABLE`
needs a USL model, and `OFFSITE CACHE TABLE` is admin-only and would attach state to the existing
REST tables. The JSON-file fallback under `runs/` was not needed.

Quirks: a view with zero rows (e.g. WIF `risks`) exports a Parquet folder with no schema, so
reading it fails with a schema-inference error; `case_file` treats that as an empty list. BONK's
`summary` snapshot was registered during the first experiment and points at
`.../casefile_snap/m_d54bf9a14eb4_summary_test1`.

Timings on this local instance (2026-10-23):

| Token | Live views (before) | First open, builds snapshots | Later reads (after) |
|---|---|---|---|
| BONK | 80.6 s (Day 1: 25-35 s) | 282 s* | 0.8-1.1 s |
| WIF | 36.2 s | 77.9 s | 0.6 s |
| ヤギ (rug case) | n/a | 32.8 s (incl. creating REST tables + views) | 1.0 s |

\* BONK's first build ran right after a driver restart. The first attempt ran 8 exports in
parallel and wedged the local driver (`docker compose restart driver` fixed it), so
exports now run one at a time.

Two more things it took to get under 2 s: the local driver runs queries one at a time, so
seven parallel reads were no faster than seven sequential ones (about 7.5 s). Reads are now
one `UNION ALL` query that returns each row as `to_json(struct(*))`. Labelled holders are
frozen as their own snapshot (`<cid>_holders_labelled_snap`) because the join alone took 3.4 s.
When `cases.json` already lists a complete snapshot set, `get_case_file` skips `open_case`'s
SHOW checks (about 2 s) and goes straight to the one query, falling back to `open_case` if it fails.
The Lightning parser rejects `''` escapes inside `RUN EXPORT ... query = '...'`, so snapshot SQL
uses `"..."` string literals.

## Zetaris notes / quirks found

- **Schema varies per token.** Zetaris infers the REST table schema from each live
  response. WIF has `creator: null` and `risks: []`, and unknown tokens have `pairs: null`.
  Plain `explode(risks)` + `r.name` would fail on those. Every view therefore parses
  through `from_json(to_json(named_struct('a', field)), '<explicit schema>')`, which
  tolerates null-typed and missing fields (they come back NULL). No view had to be
  simplified or dropped.
- **Speed.** A REST table refetches the API on every query. RugCheck views take about 10-20 s
  each (2.5 MB report), so a live case file takes 25-35 s. Each view is a separate fetch, so the
  views of one snapshot can be seconds apart (see `captured_at`). Fixed with snapshots (above).
  `CACHE TABLE` is a session cache and wasn't used.
- `SHOW TABLES IN casefile` lists SchemaStore views (`table_identifier`, uppercase), and
  `SHOW LIGHTNING TABLES <db>` lists REST tables. `open_case` checks both before creating
  anything and also treats "already exists" as success.
- All values come back from `/sql-editor/sqls/run` as strings; `case_file` converts known
  numeric/boolean columns.
