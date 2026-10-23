"""Per-token Zetaris objects ("case tables").

open_case(mint) creates, idempotently:
  DEXSCREENER_REST.<cid>_dex      REST table: DexScreener token endpoint
  RUGCHECK_REST.<cid>_rug         REST table: RugCheck token report
  casefile.<cid>_pairs            one row per DEX pair
  casefile.<cid>_summary          one row: creator, holders, score, rugged, authorities ...
  casefile.<cid>_holders          one row per top holder
  casefile.<cid>_risks            one row per RugCheck risk
  casefile.<cid>_insiders         one row per RugCheck insider network
  casefile.<cid>_markets          one row per market/LP pool RugCheck found

<cid> is "m_" + first 12 hex chars of sha1(mint). Nothing is ever dropped or replaced.

Every nested field is parsed with from_json(to_json(named_struct(...)), '<schema>').
Zetaris infers a REST table's schema from each live response, so a field that is
null for one token (WIF has creator = null, risks = []) or absent (pairs = null for
an unknown token) would otherwise change type and break a plain explode/dot-access.
An explicit schema keeps every view valid for any token; missing fields become NULL.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from casefile.zetaris import ZetarisError, run_sql

CONTAINER = "casefile"
DEX_DB = "DEXSCREENER_REST"
RUG_DB = "RUGCHECK_REST"
REGISTRY = Path(__file__).resolve().parent.parent / "cases.json"

BASE58_MINT = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

DEX_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
RUG_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"


# --- explicit schemas (Spark DDL) for the nested JSON --------------------------

_TXN = "struct<buys:bigint,sells:bigint>"
_WINDOWS = "struct<m5:double,h1:double,h6:double,h24:double>"
PAIRS_SCHEMA = (
    "struct<p:array<struct<"
    "chainId:string,dexId:string,url:string,pairAddress:string,"
    "baseToken:struct<address:string,name:string,symbol:string>,"
    "quoteToken:struct<address:string,name:string,symbol:string>,"
    "priceNative:string,priceUsd:string,"
    f"txns:struct<m5:{_TXN},h1:{_TXN},h6:{_TXN},h24:{_TXN}>,"
    f"volume:{_WINDOWS},priceChange:{_WINDOWS},"
    "liquidity:struct<usd:double,base:double,quote:double>,"
    "fdv:double,marketCap:double,pairCreatedAt:bigint>>>"
)

SUMMARY_SCHEMA = (
    "struct<"
    "mint:string,creator:string,creatorBalance:double,tokenProgram:string,tokenType:string,"
    "mintAuthority:string,freezeAuthority:string,"
    "token:struct<supply:double,decimals:int>,"
    "tokenMeta:struct<name:string,symbol:string,uri:string,mutable:boolean,updateAuthority:string>,"
    "score:bigint,score_normalised:bigint,rugged:boolean,"
    "totalHolders:bigint,totalLPProviders:bigint,"
    "totalMarketLiquidity:double,totalStableLiquidity:double,price:double,"
    "graphInsidersDetected:bigint,detectedAt:string,deployPlatform:string,"
    "launchpad:struct<name:string,platform:string,url:string>,"
    "transferFee:struct<pct:double,maxAmount:double,authority:string>,"
    "verification:struct<jup_verified:boolean,jup_strict:boolean,description:string>,"
    "lockerScanStatus:string>"
)

HOLDERS_SCHEMA = (
    "array<struct<address:string,owner:string,amount:double,uiAmount:double,"
    "pct:double,insider:boolean>>"
)
RISKS_SCHEMA = "array<struct<name:string,value:string,description:string,score:bigint,level:string>>"
INSIDERS_SCHEMA = (
    "array<struct<id:string,type:string,size:bigint,tokenAmount:double,"
    "currentHolding:double,activeAccounts:bigint>>"
)
MARKETS_SCHEMA = (
    "array<struct<pubkey:string,marketType:string,mintA:string,mintB:string,mintLP:string,"
    "lp:struct<baseMint:string,quoteMint:string,baseUSD:double,quoteUSD:double,"
    "lpLocked:double,lpUnlocked:double,lpLockedPct:double,lpLockedUSD:double>>>"
)


@dataclass
class Case:
    mint: str
    cid: str
    dex_table: str  # <db>.<table>, lowercase as used in queries
    rug_table: str | None
    views: dict[str, str]  # logical name -> casefile.<view>
    urls: dict[str, str]  # source name -> original API URL
    rugcheck_error: str | None = None


def validate_mint(mint: str) -> str:
    mint = (mint or "").strip()
    if not BASE58_MINT.match(mint):
        raise ValueError(f"Not a base58 Solana mint (32-44 chars): {mint!r}")
    return mint


def case_id(mint: str) -> str:
    return "m_" + hashlib.sha1(validate_mint(mint).encode()).hexdigest()[:12]


# --- existence checks -----------------------------------------------------------


def _lightning_databases() -> set[str]:
    return {r["name"].upper() for r in run_sql("SHOW LIGHTNING DATABASES")}


def _lightning_tables(db: str) -> set[str]:
    return {r["name"].lower() for r in run_sql(f"SHOW LIGHTNING TABLES {db}")}


def _container_views() -> set[str]:
    return {r["table_identifier"].lower() for r in run_sql(f"SHOW TABLES IN {CONTAINER}")}


def _create(statement: str) -> str:
    """Run a CREATE; 'already exists' counts as success. Returns 'created' or 'exists'."""
    try:
        run_sql(statement)
        return "created"
    except ZetarisError as e:
        if e.already_exists:
            return "exists"
        raise


def _rest_table_sql(name: str, db: str, url: str) -> str:
    return (
        f'CREATE LIGHTNING REST TABLE {name} FROM {db} REQUEST('
        f'endpoint "{url}", method "get", response_type "json", http_encoding "URLENCODED"'
        f") HEADER () BODY ()"
    )


def _view_sql(view: str, select: str) -> str:
    return f"CREATE SCHEMASTORE VIEW {view} WITH CONTAINER {CONTAINER} AS {select}"


# --- view definitions -----------------------------------------------------------


def _pairs_select(dex: str) -> str:
    return (
        "SELECT p.chainId AS chain, p.dexId AS dex, p.pairAddress AS pair_address, p.url AS url, "
        "p.baseToken.address AS base_address, p.baseToken.symbol AS symbol, p.baseToken.name AS name, "
        "p.quoteToken.address AS quote_address, p.quoteToken.symbol AS quote_symbol, "
        "CAST(p.priceUsd AS DOUBLE) AS price_usd, CAST(p.priceNative AS DOUBLE) AS price_native, "
        "p.liquidity.usd AS liquidity_usd, p.fdv AS fdv, p.marketCap AS market_cap, "
        "p.volume.m5 AS volume_m5, p.volume.h1 AS volume_h1, p.volume.h6 AS volume_h6, p.volume.h24 AS volume_24h, "
        "p.priceChange.m5 AS price_change_m5, p.priceChange.h1 AS price_change_h1, "
        "p.priceChange.h6 AS price_change_h6, p.priceChange.h24 AS price_change_24h, "
        "p.txns.h1.buys AS buys_h1, p.txns.h1.sells AS sells_h1, "
        "p.txns.h24.buys AS buys_24h, p.txns.h24.sells AS sells_24h, "
        "p.pairCreatedAt AS pair_created_at_ms "
        f"FROM {dex} "
        f"LATERAL VIEW explode(from_json(to_json(named_struct('p', pairs)), '{PAIRS_SCHEMA}').p) AS p"
    )


_SUMMARY_FIELDS = [
    "mint", "creator", "creatorBalance", "tokenProgram", "tokenType", "mintAuthority",
    "freezeAuthority", "token", "tokenMeta", "score", "score_normalised", "rugged",
    "totalHolders", "totalLPProviders", "totalMarketLiquidity", "totalStableLiquidity",
    "price", "graphInsidersDetected", "detectedAt", "deployPlatform", "launchpad",
    "transferFee", "verification", "lockerScanStatus",
]


def _summary_select(rug: str) -> str:
    packed = ", ".join(f"'{f}', {f}" for f in _SUMMARY_FIELDS)
    return (
        "SELECT s.mint AS mint, s.tokenMeta.symbol AS symbol, s.tokenMeta.name AS name, "
        "s.creator AS creator, s.creatorBalance AS creator_balance, "
        "s.score AS score, s.score_normalised AS score_normalised, s.rugged AS rugged, "
        "s.totalHolders AS total_holders, s.totalLPProviders AS total_lp_providers, "
        "s.totalMarketLiquidity AS total_market_liquidity, s.totalStableLiquidity AS total_stable_liquidity, "
        "s.price AS price, s.mintAuthority AS mint_authority, s.freezeAuthority AS freeze_authority, "
        "s.tokenMeta.mutable AS metadata_mutable, s.tokenMeta.updateAuthority AS update_authority, "
        "s.token.supply AS supply, s.token.decimals AS decimals, "
        "s.graphInsidersDetected AS graph_insiders_detected, s.detectedAt AS detected_at, "
        "s.deployPlatform AS deploy_platform, s.launchpad.name AS launchpad, "
        "s.transferFee.pct AS transfer_fee_pct, s.verification.jup_verified AS jup_verified, "
        "s.verification.jup_strict AS jup_strict, s.lockerScanStatus AS locker_scan_status, "
        "s.tokenProgram AS token_program "
        f"FROM (SELECT from_json(to_json(named_struct({packed})), '{SUMMARY_SCHEMA}') AS s FROM {rug}) x"
    )


def _array_select(rug: str, field: str, schema: str, alias: str, cols: str) -> str:
    return (
        f"SELECT {cols} FROM {rug} "
        f"LATERAL VIEW explode(from_json(to_json(named_struct('a', {field})), 'struct<a:{schema}>').a) AS {alias}"
    )


def _holders_select(rug: str) -> str:
    return _array_select(
        rug, "topHolders", HOLDERS_SCHEMA, "h",
        "h.address AS token_account, h.owner AS owner, h.pct AS pct, h.uiAmount AS ui_amount, "
        "h.insider AS insider",
    )


def _risks_select(rug: str) -> str:
    return _array_select(
        rug, "risks", RISKS_SCHEMA, "r",
        "r.name AS name, r.level AS level, r.score AS score, r.description AS description, r.value AS value",
    )


def _insiders_select(rug: str) -> str:
    return _array_select(
        rug, "insiderNetworks", INSIDERS_SCHEMA, "n",
        "n.id AS network_id, n.type AS type, n.size AS size, n.activeAccounts AS active_accounts, "
        "n.tokenAmount AS token_amount, n.currentHolding AS current_holding",
    )


def _markets_select(rug: str) -> str:
    return _array_select(
        rug, "markets", MARKETS_SCHEMA, "m",
        "m.pubkey AS market, m.marketType AS market_type, m.mintA AS mint_a, m.mintB AS mint_b, "
        "m.lp.baseUSD AS base_usd, m.lp.quoteUSD AS quote_usd, m.lp.lpLockedPct AS lp_locked_pct, "
        "m.lp.lpLockedUSD AS lp_locked_usd",
    )


# --- registry -------------------------------------------------------------------


def _load_registry() -> dict:
    try:
        return json.loads(REGISTRY.read_text())
    except (OSError, ValueError):
        return {}


def _save(case: Case) -> None:
    reg = _load_registry()
    reg[case.mint] = asdict(case)
    REGISTRY.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n")


# --- public API -----------------------------------------------------------------


def open_case(mint: str, verbose: bool = False) -> Case:
    """Create (if missing) every Zetaris object for this token and return their names."""
    mint = validate_mint(mint)
    cid = case_id(mint)
    log = print if verbose else (lambda *a, **k: None)

    dex_url, rug_url = DEX_URL.format(mint=mint), RUG_URL.format(mint=mint)
    dex_table = f"{DEX_DB.lower()}.{cid}_dex"
    rug_table = f"{RUG_DB.lower()}.{cid}_rug"
    case = Case(mint=mint, cid=cid, dex_table=dex_table, rug_table=rug_table, views={},
                urls={"dexscreener": dex_url, "rugcheck": rug_url})

    views_present = _container_views()

    def ensure_view(key: str, select: str) -> None:
        view = f"{cid}_{key}"
        if view in views_present:
            log(f"  view {CONTAINER}.{view}: exists")
        else:
            log(f"  view {CONTAINER}.{view}: {_create(_view_sql(view, select))}")
        case.views[key] = f"{CONTAINER}.{view}"

    # DexScreener: the database was created by hand and must already exist.
    if f"{cid}_dex" in _lightning_tables(DEX_DB):
        log(f"  table {dex_table}: exists")
    else:
        log(f"  table {dex_table}: {_create(_rest_table_sql(f'{cid}_dex', DEX_DB, dex_url))}")
    ensure_view("pairs", _pairs_select(dex_table))

    # RugCheck: failures here must not take DexScreener down with them.
    try:
        if RUG_DB not in _lightning_databases():
            log(f"  database {RUG_DB}: "
                + _create(f'CREATE LIGHTNING DATABASE {RUG_DB} DESCRIBE BY "RugCheck REST source"'))
        if f"{cid}_rug" in _lightning_tables(RUG_DB):
            log(f"  table {rug_table}: exists")
        else:
            log(f"  table {rug_table}: {_create(_rest_table_sql(f'{cid}_rug', RUG_DB, rug_url))}")
        ensure_view("summary", _summary_select(rug_table))
        ensure_view("holders", _holders_select(rug_table))
        ensure_view("risks", _risks_select(rug_table))
        ensure_view("insiders", _insiders_select(rug_table))
        ensure_view("markets", _markets_select(rug_table))
    except ZetarisError as e:
        case.rugcheck_error = str(e)
        log(f"  RugCheck setup failed: {e}")

    _save(case)
    return case
