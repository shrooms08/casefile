"""Assemble a token's case file by querying the casefile.* views through Zetaris only."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from casefile.sources import Case, open_case
from casefile.zetaris import ZetarisError, run_sql

# Zetaris returns every value as a string; these columns get converted back.
_INT = {
    "buys_h1", "sells_h1", "buys_24h", "sells_24h", "pair_created_at_ms", "score",
    "score_normalised", "total_holders", "total_lp_providers", "decimals",
    "graph_insiders_detected", "size", "active_accounts",
}
_FLOAT = {
    "price_usd", "price_native", "liquidity_usd", "fdv", "market_cap", "volume_m5", "volume_h1",
    "volume_h6", "volume_24h", "price_change_m5", "price_change_h1", "price_change_h6",
    "price_change_24h", "creator_balance", "total_market_liquidity", "total_stable_liquidity",
    "price", "supply", "transfer_fee_pct", "pct", "ui_amount", "token_amount", "current_holding",
    "base_usd", "quote_usd", "lp_locked_pct", "lp_locked_usd",
}
_BOOL = {"rugged", "metadata_mutable", "jup_verified", "jup_strict", "insider"}

# Per-view query: ORDER BY / LIMIT keep the payload small for big tokens.
_QUERIES = {
    "pairs": "SELECT * FROM {v} ORDER BY liquidity_usd DESC",
    "summary": "SELECT * FROM {v}",
    "holders": "SELECT * FROM {v} ORDER BY pct DESC",
    "risks": "SELECT * FROM {v} ORDER BY score DESC",
    "insiders": "SELECT * FROM {v} ORDER BY size DESC",
    "markets": "SELECT * FROM {v} ORDER BY lp_locked_usd DESC, quote_usd DESC LIMIT 25",
}


def _coerce(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if v is None or v == "null":
            out[k] = None
        elif k in _INT:
            out[k] = int(float(v))
        elif k in _FLOAT:
            out[k] = float(v)
        elif k in _BOOL:
            out[k] = str(v).lower() == "true"
        else:
            out[k] = v
    return out


def _query(view: str, key: str) -> list[dict[str, Any]]:
    return [_coerce(r) for r in run_sql(_QUERIES[key].format(v=view))]


def get_case_file(mint: str) -> dict[str, Any]:
    case: Case = open_case(mint)
    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    if case.rugcheck_error:
        errors["rugcheck_setup"] = case.rugcheck_error

    with ThreadPoolExecutor(max_workers=len(case.views) or 1) as pool:
        futures = {key: pool.submit(_query, view, key) for key, view in case.views.items()}
        for key, fut in futures.items():
            try:
                results[key] = fut.result()
            except ZetarisError as e:
                errors[key] = str(e)
                results[key] = []

    summary = (results.get("summary") or [{}])[0]
    sources = [
        {
            "view": view,
            "kind": key,
            "api": case.urls["dexscreener" if key == "pairs" else "rugcheck"],
            "via": case.dex_table if key == "pairs" else case.rug_table,
        }
        for key, view in case.views.items()
    ]

    return {
        "mint": case.mint,
        "case_id": case.cid,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "pairs": results.get("pairs", []),
        "top_holders": results.get("holders", []),
        "risks": results.get("risks", []),
        "insider_networks": results.get("insiders", []),
        "markets": results.get("markets", []),
        "sources": sources,
        "errors": errors,
    }
