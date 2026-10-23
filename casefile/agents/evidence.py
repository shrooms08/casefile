"""Evidence slices for the agents, computed fields, and a mechanical evidence check.

Everything here is derived from the frozen snapshot rows (or recalled H-MEM facts). No
verdicts: computed fields are plain arithmetic with the formula written next to them.
"""

from __future__ import annotations

import time
from typing import Any

from casefile.agents.state import CaseState

# Short table names the agents use -> case-file keys.
TABLES = {
    "summary": "summary", "holders": "top_holders", "pairs": "pairs", "markets": "markets",
    "risks": "risks", "insiders": "insider_networks", "lockers": "lockers",
}
NOT_OWNERSHIP = {"AMM", "LOCKER"}  # labelled pools and lockers hold tokens on behalf of others
ESTABLISHED_DAYS, ESTABLISHED_HOLDERS = 180, 100_000


def _own_pairs(cf: dict) -> list[dict]:
    return [p for p in cf["pairs"] if p.get("base_address") == cf["mint"]] or cf["pairs"]


def _pct_of_supply(amount: float, supply: float, nets: list, formula: str) -> dict:
    if not nets:
        return {"value": 0.0, "formula": formula}
    if not supply:
        return {"value": None, "formula": formula, "note": "unreliable: no supply"}
    pct = round(100 * amount / supply, 2)
    if pct > 100:  # transfer-graph amounts can exceed supply (counted more than once)
        return {"value": None, "formula": formula, "note": f"unreliable: {pct}% exceeds 100% of supply"}
    return {"value": pct, "formula": formula}


def computed_fields(cf: dict, memories: dict[str, list[dict]]) -> dict[str, Any]:
    s, holders = cf["summary"], cf["top_holders"]
    own = _own_pairs(cf)
    created = [p["pair_created_at_ms"] for p in own if p.get("pair_created_at_ms")]
    age_days = round((time.time() * 1000 - min(created)) / 86_400_000, 1) if created else None
    top = own[0] if own else {}
    custodians = {w for w, facts in memories.items() if any(f["kind"] == "derived:custodian" for f in facts)}

    def share(rows):
        return round(sum(h.get("pct") or 0 for h in rows), 2)

    top10 = holders[:10]
    ownership = [h for h in top10 if (h.get("label_type") or "").upper() not in NOT_OWNERSHIP]
    total_holders = s.get("total_holders") or 0
    buys, sells = top.get("buys_24h"), top.get("sells_24h")
    # Only pairs holding real liquidity (>= 10% of the top pair's) count for the worst move:
    # a dust pair's -60% says nothing about the token.
    floor = 0.1 * (top.get("liquidity_usd") or 0)
    deep = [p for p in own if (p.get("liquidity_usd") or 0) >= floor] or own[:1]
    changes = [p.get(k) for p in deep for k in ("price_change_h1", "price_change_h6", "price_change_24h")
               if p.get(k) is not None]
    supply = s.get("supply") or 0
    nets = cf["insider_networks"]
    net_amounts = [n.get("token_amount") or 0 for n in nets]
    own_liq = round(sum(p.get("liquidity_usd") or 0 for p in own), 2)
    return {
        "worst_price_change_pct": {"value": min(changes) if changes else None,
                                   "formula": "lowest price_change_h1/h6/24h across own pairs with >= 10% of the top pair's liquidity"},
        "own_liquidity_usd": {"value": own_liq, "formula": "sum liquidity_usd of own pairs"},
        "top_pair_liquidity_usd": {"value": top.get("liquidity_usd"), "formula": "liquidity_usd of the top own pair"},
        "top_pair_fdv_usd": {"value": top.get("fdv"), "formula": "fdv of the top own pair"},
        "volume_to_liquidity_24h": {"value": round(top["volume_24h"] / top["liquidity_usd"], 1)
                                    if top.get("volume_24h") and top.get("liquidity_usd") else None,
                                    "formula": "top own pair volume_24h / liquidity_usd"},
        "insider_networks_supply_pct": _pct_of_supply(sum(net_amounts), supply, nets,
                                                      "100 * sum(insiders.token_amount) / summary.supply"),
        "largest_insider_network_supply_pct": _pct_of_supply(max(net_amounts, default=0), supply, nets,
                                                             "100 * max(insiders.token_amount) / summary.supply"),
        "danger_risks": {"value": [r["name"] for r in cf["risks"] if r.get("level") == "danger"],
                         "formula": "names of risks with level danger"},
        "pair_age_days": {"value": age_days, "formula": "now - oldest own pair pair_created_at_ms"},
        "established": {"value": bool(age_days and age_days > ESTABLISHED_DAYS and total_holders > ESTABLISHED_HOLDERS),
                        "formula": f"pair_age_days > {ESTABLISHED_DAYS} AND summary.total_holders > {ESTABLISHED_HOLDERS}"},
        "top10_pct_all": {"value": share(top10), "formula": "sum holders.pct of the top 10 rows"},
        "top10_pct_excluding_pools_lockers": {
            "value": share(ownership),
            "formula": "top 10 holders.pct minus rows labelled AMM or LOCKER"},
        "top10_pct_excluding_pools_lockers_custodians": {
            "value": share([h for h in ownership if h.get("owner") not in custodians]),
            "formula": "as above, also minus wallets H-MEM marks likely custodian"},
        "insider_flagged_holders": {"value": sum(1 for h in holders if h.get("insider")),
                                    "formula": "count holders.insider = true"},
        "buy_sell_ratio_24h": {"value": round(buys / sells, 2) if buys and sells else None,
                               "formula": "top own pair buys_24h / sells_24h"},
        "liquidity_to_fdv": {"value": round(top["liquidity_usd"] / top["fdv"], 4)
                             if top.get("liquidity_usd") and top.get("fdv") else None,
                             "formula": "top own pair liquidity_usd / fdv"},
        "own_pair_count": {"value": len(own), "formula": "DexScreener pairs whose base token is this mint"},
    }


def _holder_row(h: dict) -> dict:
    return {k: h.get(k) for k in ("owner", "pct", "insider", "label", "label_type")}


def _memory_lines(state: CaseState, wallets: list[str]) -> list[dict]:
    out = []
    for w in wallets:
        for f in state.memories.get(w, []):
            out.append({"wallet": w, "kind": f["kind"], "fact": f["content"],
                        "source_case": f.get("case_id"), "memory_id": f["memory_id"]})
    return out


def slices(state: CaseState) -> dict[str, dict[str, Any]]:
    cf, s, c = state.case_file, state.case_file["summary"], state.computed
    own = _own_pairs(cf)
    holders = cf["top_holders"]
    holder_wallets = [h.get("owner") for h in holders[:20] if h.get("owner")]
    pick = lambda d, keys: {k: d.get(k) for k in keys}
    return {
        "holders": {
            "summary": pick(s, ("symbol", "total_holders", "graph_insiders_detected", "creator")),
            "holders": [_holder_row(h) for h in holders[:20]],
            "insiders": [pick(n, ("network_id", "type", "size", "token_amount", "active_accounts"))
                         for n in cf["insider_networks"][:5]],
            "insider_network_count": len(cf["insider_networks"]),
            "computed": pick(c, ("established", "pair_age_days", "top10_pct_all", "top10_pct_excluding_pools_lockers",
                                 "top10_pct_excluding_pools_lockers_custodians", "insider_flagged_holders",
                                 "insider_networks_supply_pct", "largest_insider_network_supply_pct")),
            "memory": _memory_lines(state, holder_wallets),
        },
        "liquidity": {
            "summary": pick(s, ("symbol", "total_market_liquidity", "total_stable_liquidity", "total_lp_providers",
                                "price")),
            "pairs": [pick(p, ("dex", "quote_symbol", "liquidity_usd", "fdv", "market_cap", "volume_24h",
                               "price_change_h1", "price_change_h6", "price_change_24h", "buys_24h",
                               "sells_24h", "pair_created_at_ms")) for p in own[:5]],
            "markets": [pick(m, ("market_type", "lp_locked_pct", "lp_locked_usd", "base_usd", "quote_usd"))
                        for m in cf["markets"][:5]],
            "lockers": [pick(l, ("type", "usdc_locked", "unlock_date")) for l in cf["lockers"][:5]],
            "locker_count": len(cf["lockers"]),
            "computed": pick(c, ("established", "pair_age_days", "worst_price_change_pct", "own_liquidity_usd",
                                 "top_pair_liquidity_usd", "top_pair_fdv_usd", "volume_to_liquidity_24h",
                                 "buy_sell_ratio_24h", "liquidity_to_fdv", "own_pair_count", "danger_risks")),
        },
        "deployer": {
            "summary": pick(s, ("symbol", "creator", "creator_balance", "mint_authority", "freeze_authority",
                                "update_authority", "metadata_mutable", "score", "score_normalised", "rugged",
                                "graph_insiders_detected", "deploy_platform", "launchpad", "detected_at",
                                "transfer_fee_pct", "jup_verified")),
            "risks": [pick(r, ("name", "level", "value", "description")) for r in cf["risks"]],
            "insiders": [pick(n, ("network_id", "type", "size", "token_amount", "current_holding"))
                         for n in cf["insider_networks"][:5]],
            "insider_network_count": len(cf["insider_networks"]),
            "computed": pick(c, ("established", "pair_age_days", "danger_risks", "insider_networks_supply_pct",
                                 "largest_insider_network_supply_pct", "worst_price_change_pct")),
            "memory": _memory_lines(state, [s.get("creator")] if s.get("creator") else []),
        },
    }


def table_columns(state: CaseState) -> dict[str, list[str]]:
    cf = state.case_file
    cols = {}
    for short, key in TABLES.items():
        rows = cf.get(key)
        rows = [rows] if isinstance(rows, dict) else rows
        cols[short] = sorted({k for r in rows or [] for k in r})
    return cols


# --- mechanical evidence check -----------------------------------------------------------

def _close(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= max(0.011, 0.02 * abs(fb))
    except (TypeError, ValueError):
        sa, sb = str(a).strip().lower(), str(b).strip().lower()
        return sa == sb or (len(sa) > 3 and (sa in sb or sb in sa))


def check_evidence(state: CaseState, item: dict) -> tuple[bool, str]:
    """Is the cited value really in the cited table/field? Returns (verified, note)."""
    table, fld, value = item.get("table"), item.get("field"), item.get("value")
    if table == "H-MEM":
        facts = [f for fs in state.memories.values() for f in fs]
        ok = any(_close(value, f["content"]) or str(value).lower() in f["content"].lower() for f in facts) \
            or any(f["memory_id"] == fld for f in facts)
        return ok, "matches a recalled H-MEM fact" if ok else "no recalled H-MEM fact matches"
    if table == "computed":
        c = state.computed.get(fld)
        if c is None:
            return False, f"no computed field {fld}"
        cv = c["value"]
        if isinstance(cv, list):
            ok = _close(value, cv) or (isinstance(value, list) and all(any(_close(x, y) for y in cv) for x in value)) \
                or any(_close(value, y) for y in cv)
            return ok, f"computed {fld} = {cv}"
        return _close(value, cv), f"computed {fld} = {cv}"
    key = TABLES.get(table or "")
    if not key:
        return False, f"unknown table {table}"
    rows = state.case_file.get(key)
    rows = [rows] if isinstance(rows, dict) else (rows or [])
    leaf = (fld or "").split(".")[-1].split("[")[0]
    present = [r.get(leaf) for r in rows if leaf in r]
    if not present:
        return False, f"{table} has no field {leaf}"
    if value in (None, "null", "None") and any(v is None for v in present):
        return True, f"{table}.{leaf} is null"
    if any(_close(value, v) for v in present):
        return True, f"{table}.{leaf} contains {value}"
    return False, f"{table}.{leaf} has {present[:3]}, not {value}"


def expand_evidence(state: CaseState, item: dict) -> dict:
    """Short table name -> full snapshot table + source API URL; adds the mechanical check."""
    table = item.get("table")
    out = {"table": table, "field": item.get("field"), "value": item.get("value")}
    if table == "H-MEM":
        src = next((f.get("case_id") for fs in state.memories.values() for f in fs
                    if f["memory_id"] == item.get("field") or str(item.get("value", "")).lower() in f["content"].lower()),
                   None)
        out.update(table="H-MEM", source_api_url=f"hmem://casefile/{src or 'unknown'}", source_case=src)
    elif table == "computed":
        out.update(table="computed", source_api_url=None,
                   formula=(state.computed.get(item.get("field") or "") or {}).get("formula"))
    else:
        out.update(table=state.snapshot_tables.get(table, table),
                   source_api_url=state.source_urls.get("dexscreener" if table == "pairs" else "rugcheck"))
    ok, note = check_evidence(state, item)
    out.update(verified=ok, check=note)
    return out
