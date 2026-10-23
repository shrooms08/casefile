"""Assemble a token's case file by querying Zetaris only.

By default it reads the frozen snapshot tables (CASEFILE_SNAP.<cid>_<view>_snap, see
casefile/snapshot.py), which open_case creates once per token from the casefile.* views.
fresh=True skips the snapshots and queries the live views (25-35 s for a big token).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from casefile.sources import Case, _load_registry, open_case, validate_mint
from casefile.zetaris import ZetarisError, run_sql

# Zetaris returns every value as a string; these columns get converted back.
_INT = {
    "buys_h1", "sells_h1", "buys_24h", "sells_24h", "pair_created_at_ms", "score",
    "score_normalised", "total_holders", "total_lp_providers", "decimals",
    "graph_insiders_detected", "size", "active_accounts", "unlock_date",
}
_FLOAT = {
    "price_usd", "price_native", "liquidity_usd", "fdv", "market_cap", "volume_m5", "volume_h1",
    "volume_h6", "volume_24h", "price_change_m5", "price_change_h1", "price_change_h6",
    "price_change_24h", "creator_balance", "total_market_liquidity", "total_stable_liquidity",
    "price", "supply", "transfer_fee_pct", "pct", "ui_amount", "token_amount", "current_holding",
    "base_usd", "quote_usd", "lp_locked_pct", "lp_locked_usd", "usdc_locked",
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
    "lockers": "SELECT * FROM {v} ORDER BY usdc_locked DESC",
}

# Keys the case file reads (known_accounts is only used for labels).
_READ = ("pairs", "summary", "holders", "risks", "insiders", "markets", "lockers")

# Python-side ordering for snapshot reads: (sort column, descending, limit).
_ORDER = {
    "pairs": ("liquidity_usd", None), "holders": ("pct", None), "risks": ("score", None),
    "insiders": ("size", None), "markets": ("lp_locked_usd", 25), "lockers": ("usdc_locked", None),
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


def _snapshot_tables(case: Case) -> dict[str, dict] | None:
    """key -> snapshot info for every key the case file reads, or None if any is missing."""
    snaps = dict(case.snapshots or {})
    if snaps.get("holders_labelled", {}).get("table"):
        snaps["holders"] = snaps["holders_labelled"]
    needed = [k for k in _READ if k in case.views]
    if not needed or any(not (snaps.get(k) or {}).get("table") or "rows" not in snaps[k] for k in needed):
        return None
    return {k: snaps[k] for k in needed}


def _read_snapshots(snaps: dict[str, dict]) -> dict[str, list[dict[str, Any]]]:
    """All snapshot tables in ONE Zetaris query (the local driver runs queries one at a time,
    so one round trip beats seven parallel ones)."""
    parts = [f"SELECT '{k}' AS k, to_json(struct(*)) AS j FROM {v['table']}"
             for k, v in snaps.items() if v["rows"]]
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in snaps}
    if not parts:
        return out
    for r in run_sql(" UNION ALL ".join(parts), limit=100000):
        out[r["k"]].append(json.loads(r["j"]))
    for k, (col, limit) in _ORDER.items():
        if k in out:
            # NULLs last, like ORDER BY ... DESC on the live views.
            ties = "quote_usd" if k == "markets" else col
            out[k].sort(key=lambda row: (row.get(col) is None, -(row.get(col) or 0),
                                         -(row.get(ties) or 0)))
            if limit:
                out[k] = out[k][:limit]
    return out


def _read_live(case: Case) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    results: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    keys = [k for k in _READ if k in case.views]
    with ThreadPoolExecutor(max_workers=len(keys) or 1) as pool:
        futures = {k: pool.submit(lambda k=k: [_coerce(r) for r in run_sql(
            _QUERIES[k].format(v=case.views[k]))]) for k in keys}
        for k, fut in futures.items():
            try:
                results[k] = fut.result()
            except ZetarisError as e:
                errors[k] = str(e)
                results[k] = []
    return results, errors


def _registered_case(mint: str) -> Case | None:
    entry = _load_registry().get(mint)
    if not entry:
        return None
    try:
        return Case(**entry)
    except TypeError:
        return None


def get_case_file(mint: str, fresh: bool = False) -> dict[str, Any]:
    """Case file for a mint. Reads the frozen snapshots (one Zetaris query) unless fresh=True."""
    mint = validate_mint(mint)
    errors: dict[str, str] = {}
    results = None
    case = None if fresh else _registered_case(mint)
    snaps = _snapshot_tables(case) if case else None
    if snaps:  # fast path: registry already lists a complete snapshot set
        try:
            results = _read_snapshots(snaps)
        except ZetarisError:
            results = None  # e.g. a snapshot table went missing; re-check below
    if results is None:
        case = open_case(mint, snapshot=not fresh)
        snaps = None if fresh else _snapshot_tables(case)
        if case.snapshot_error and not fresh:
            errors["snapshot_setup"] = case.snapshot_error
        if snaps:
            try:
                results = _read_snapshots(snaps)
            except ZetarisError as e:
                errors["snapshot_read"] = str(e)
        if results is None:
            results, live_errors = _read_live(case)
            errors.update(live_errors)
    if case.rugcheck_error:
        errors["rugcheck_setup"] = case.rugcheck_error
    use_snap = bool(snaps) and "snapshot_read" not in errors
    tables = {k: v["table"] for k, v in (snaps or {}).items()}

    summary = (results.get("summary") or [{}])[0]
    captured = sorted({r.get("captured_at") for rows in results.values() for r in rows
                       if r.get("captured_at")})
    sources = [
        {
            "kind": key,
            "view": view,
            "read_from": tables.get(key, view),
            "snapshot_sql": (snaps or {}).get(key, {}).get("sql") if use_snap else None,
            "api": case.urls["dexscreener" if key == "pairs" else "rugcheck"],
            "via": case.dex_table if key == "pairs" else case.rug_table,
        }
        for key, view in case.views.items()
    ]

    return {
        "mint": case.mint,
        "case_id": case.cid,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "snapshot" if use_snap else "live",
        "captured_at": {"first": captured[0], "last": captured[-1]} if captured else None,
        "summary": summary,
        "pairs": results.get("pairs", []),
        "top_holders": results.get("holders", []),
        "risks": results.get("risks", []),
        "insider_networks": results.get("insiders", []),
        "markets": results.get("markets", []),
        "lockers": results.get("lockers", []),
        "sources": sources,
        "errors": errors,
    }
