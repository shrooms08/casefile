"""Day 1 check: print a compact case file for one Solana mint.

Usage: uv run python scripts/day1_check.py <mint>
"""

import sys
import time
from datetime import datetime, timezone

from casefile.case_file import get_case_file


def _usd(x):
    return "n/a" if x is None else f"${x:,.0f}"


def _pct(x):
    return "n/a" if x is None else f"{x:+.2f}%"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    t0 = time.time()
    cf = get_case_file(sys.argv[1])
    s, pairs = cf["summary"], cf["pairs"]
    mint = cf["mint"]
    own = [p for p in pairs if p.get("base_address") == mint] or pairs
    best = own[0] if own else {}

    symbol = s.get("symbol") or best.get("symbol") or "?"
    print(f"CASE FILE  {symbol}  ({mint})   case_id={cf['case_id']}")
    print(f"  retrieved {cf['retrieved_at']} in {time.time() - t0:.1f}s")
    if best:
        created = best.get("pair_created_at_ms")
        created_s = (datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat()
                     if created else "n/a")
        print(f"  best pair : {best.get('dex')} {best.get('symbol')}/{best.get('quote_symbol')} "
              f"{best.get('pair_address')}")
        print(f"              liquidity {_usd(best.get('liquidity_usd'))}  24h {_pct(best.get('price_change_24h'))}"
              f"  vol24h {_usd(best.get('volume_24h'))}  buys/sells24h "
              f"{best.get('buys_24h')}/{best.get('sells_24h')}  created {created_s}")
    print(f"  pairs     : {len(pairs)} on DexScreener")
    if s:
        print(f"  holders   : {s.get('total_holders'):,}" if s.get("total_holders") is not None
              else "  holders   : n/a")
        print(f"  creator   : {s.get('creator') or 'n/a'}")
        print(f"  rugcheck  : score {s.get('score')} (normalised {s.get('score_normalised')})  "
              f"rugged={s.get('rugged')}  mint_auth={s.get('mint_authority') or 'none'}  "
              f"freeze_auth={s.get('freeze_authority') or 'none'}  "
              f"insiders_detected={s.get('graph_insiders_detected')}")
    print("  top 5 holders:")
    for h in cf["top_holders"][:5]:
        flag = "INSIDER" if h.get("insider") else "-"
        print(f"    {h.get('pct', 0):6.2f}%  {h.get('owner')}  {flag}")
    print("  risks:" + ("" if cf["risks"] else " none reported"))
    for r in cf["risks"]:
        print(f"    [{r.get('level')}] {r.get('name')} (score {r.get('score')}): {r.get('description')}")
    nets = cf["insider_networks"]
    if nets:
        print(f"  insider networks: {len(nets)}, largest {nets[0].get('size')} accounts "
              f"({nets[0].get('type')})")
    print("  zetaris views used:")
    for src in cf["sources"]:
        print(f"    {src['view']:<32} <- {src['via']}")
    if cf["errors"]:
        print("  ERRORS:")
        for k, v in cf["errors"].items():
            print(f"    {k}: {v}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
