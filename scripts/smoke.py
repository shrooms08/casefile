"""Smoke test: case file from Zetaris -> one Nightshift call -> three evidence lines.

Usage: uv run python scripts/smoke.py <mint>
"""

import json
import sys
import time

from casefile import llm
from casefile.case_file import get_case_file

INSTRUCTION = ("In exactly 3 short lines: what does this evidence suggest about this token, "
               "citing the specific field for each claim.")

_SUMMARY_KEYS = (
    "symbol", "name", "creator", "creator_balance", "score", "score_normalised", "rugged",
    "total_holders", "total_lp_providers", "total_market_liquidity", "mint_authority",
    "freeze_authority", "metadata_mutable", "graph_insiders_detected", "launchpad",
    "deploy_platform", "detected_at", "transfer_fee_pct", "jup_verified",
)


def _pick(row: dict, keys) -> dict:
    return {k: row.get(k) for k in keys if row.get(k) is not None}


def compact(cf: dict) -> dict:
    """Small JSON view of the case file: the fields an analyst would cite."""
    mint = cf["mint"]
    own = [p for p in cf["pairs"] if p.get("base_address") == mint] or cf["pairs"]
    return {
        "mint": mint,
        "summary": _pick(cf["summary"], _SUMMARY_KEYS),
        "top_pairs": [_pick(p, ("dex", "quote_symbol", "liquidity_usd", "fdv", "market_cap", "volume_24h",
                                "price_change_h1", "price_change_h6", "price_change_24h", "buys_24h",
                                "sells_24h", "pair_created_at_ms")) for p in own[:3]],
        "pair_count": len(cf["pairs"]),
        "top_holders": [_pick(h, ("owner", "pct", "insider", "label", "label_type"))
                        for h in cf["top_holders"][:10]],
        "risks": [_pick(r, ("name", "level", "value")) for r in cf["risks"]],
        "insider_networks": {
            "count": len(cf["insider_networks"]),
            "largest": [_pick(n, ("type", "size", "token_amount", "current_holding", "active_accounts"))
                        for n in cf["insider_networks"][:3]],
        },
        "markets": [_pick(m, ("market_type", "lp_locked_pct", "lp_locked_usd", "quote_usd"))
                    for m in cf["markets"][:3]],
        "lockers": len(cf["lockers"]),
        "captured_at": cf.get("captured_at"),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    t0 = time.time()
    cf = get_case_file(sys.argv[1])
    t_case = time.time() - t0
    evidence = compact(cf)
    messages = [
        {"role": "system", "content": (
            "You are a careful on-chain analyst. Use only the evidence given. Reply in plain text: "
            "exactly three lines, no JSON, no brackets, no bullets, no markdown. Each line is one "
            "short claim followed by the field it rests on, for example: "
            "Liquidity is almost gone - top_pairs[0].liquidity_usd=2397")},
        {"role": "user", "content": f"{INSTRUCTION}\n\nEVIDENCE (JSON):\n{json.dumps(evidence, default=str)}"},
    ]
    r = llm.chat(messages, role="fast", case_id=cf["case_id"], reasoning_effort="low")
    total = time.time() - t0

    symbol = cf["summary"].get("symbol") or "?"
    print(f"SMOKE {symbol} {cf['mint']}  case_id={cf['case_id']}  mode={cf['mode']}")
    lines = [ln.strip() for ln in r.content.strip().splitlines() if ln.strip()]
    for ln in lines:
        print(f"  {ln}")
    if len(lines) != 3:
        print(f"  (model returned {len(lines)} lines, not 3)")
    print(f"routed_model : {r.routed_model}")
    print(f"receipt_id   : {r.receipt_id}")
    print(f"cross_check  : {r.cross_check}")
    print(f"timing       : case file {t_case:.1f}s, llm {r.latency_ms / 1000:.1f}s, total {total:.1f}s")
    if cf["errors"]:
        print(f"case file errors: {cf['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
