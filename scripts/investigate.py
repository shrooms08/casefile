"""Run a full Casefile investigation on one mint and print a live trace.

Usage: uv run python scripts/investigate.py <mint> [--json]
Opens the case if needed (reuses CASEFILE_SNAP snapshots), runs planner -> investigators ->
skeptic -> verdict, stores H-MEM memories. The full trace is in runs/<case_id>/trace.jsonl.
"""

import json
import sys
import time

from casefile.agents.loop import investigate

T0 = time.time()


def _short(m: str | None) -> str:
    return (m or "-").split("/")[-1]


def show(e: dict) -> None:
    t = f"{time.time() - T0:6.1f}s"
    step, agent, out = e["step"], e["agent"], e["output"]
    model = f" [{_short(e['model'])}]" if e.get("model") else ""
    if step == "start":
        print(f"{t}  casefile   opened {out['symbol']} from {len(out['snapshot_tables'])} snapshot tables")
    elif step == "memory_recall":
        print(f"{t}  h-mem      recalled {len(out['facts'])} fact(s) for {out['wallets_with_memory']} of "
              f"{out['wallets_asked']} wallets")
        derived = [f for f in out["facts"] if f["kind"] == "derived:custodian"]
        for f in derived + [f for f in out["facts"] if f["kind"] != "derived:custodian"][:6]:
            print(f"{'':10}   - [{f['kind']}{' from ' + f['source_case'] if f.get('source_case') else ''}] {f['fact'][:140]}")
        if len(out["facts"]) > len(derived) + 6:
            print(f"{'':10}   ... {len(out['facts']) - len(derived) - 6} more")
    elif step == "computed":
        c = {k: v["value"] for k, v in out.items()}
        print(f"{t}  casefile   established={c['established']} pair_age_days={c['pair_age_days']} "
              f"top10%={c['top10_pct_all']} (excl pools/lockers {c['top10_pct_excluding_pools_lockers']})")
    elif step == "plan":
        print(f"{t}  planner{model}  {len(out['questions'])} questions")
        for q in out["questions"]:
            print(f"{'':10}   {q.get('id')} -> {q['investigator']}: {q['question'][:140]}")
    elif step == "query":
        print(f"{t}  {agent:<10} query_case -> {out['rows']} rows: {e['sql'][:150]}")
    elif step in ("query_rejected", "query_error"):
        print(f"{t}  {agent:<10} query refused: {out['error'][:150]}")
    elif step == "investigate":
        what = "asks for a query" if out.get("action") == "query" else f"{len(out.get('claims', []))} claim(s)"
        print(f"{t}  {agent:<10}{model} {what}")
    elif step == "claims":
        for c in out:
            ok = sum(1 for x in c["evidence"] if x["verified"])
            print(f"{'':10}   {c['id']} ({c['confidence']}, evidence {ok}/{len(c['evidence'])} verified): {c['claim'][:150]}")
    elif step == "decision":
        print(f"{t}  skeptic    {out['decision'].upper():6} {out['id']} ({out['round']}): {out['reason'][:150]}")
    elif step == "revised_claims":
        for c in out:
            print(f"{t}  {agent:<10} revised {c['id']}: {c['claim'][:150]}")
    elif step == "dropped":
        print(f"{t}  {agent:<10} dropped {out['id']}: {out['why']}")
    elif step.endswith("_fallback"):
        print(f"{t}  {agent:<10} deep model kept timing out; one try on the fast model")
    elif step.endswith("_invalid"):
        print(f"{t}  {agent:<10}{model} invalid JSON, retrying: {'; '.join(out['errors'])[:150]}")
    elif step.endswith("_error") or step.endswith("_failed"):
        print(f"{t}  {agent:<10} ERROR: {str(out.get('error'))[:200]}")
    elif step in ("review", "re_review"):
        pass  # decisions are printed one by one
    elif step == "verdict":
        print(f"{t}  verdict{model}  {out['label']}")
    elif step == "memory_observe":
        print(f"{t}  h-mem      observed this case: {out['created']} new, {out['updated']} updated; "
              f"derived {len(out['derived_ids'])} custodian note(s)")
    elif step == "memory_store":
        print(f"{t}  h-mem      stored {out['created']} new, {out['updated']} updated, {out['unchanged']} unchanged; "
              f"derived {len(out['derived_ids'])} custodian note(s)")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    state = investigate(args[0], on_event=show)
    v = state.verdict
    total = time.time() - T0
    print("\n" + "=" * 78)
    print(f"VERDICT  {v['label']}  -  {state.symbol} ({state.mint})")
    print(f"  {v['one_line']}")
    for w in v["why"]:
        c = state.claims[w["claim_id"]]
        cites = "; ".join(f"{x['table'].split('.')[-1]}.{x['field']}={x['value']}" for x in c["evidence"])
        print(f"  - [{w['claim_id']}] {w['sentence']}  ({cites})")
    print(f"  what would change my mind: {v['what_would_change_my_mind']}")
    acc = len(state.accepted())
    rej = len({d['id'] for d in state.dropped})
    print(f"  claims: {acc} accepted, {rej} rejected/dropped, {len(state.claims)} total")
    print(f"  models: {', '.join(v['models_used'])}")
    print(f"  {state.llm_calls} LLM calls, {total:.0f}s total, trace runs/{state.case_id}/trace.jsonl "
          f"(run {state.run_id})")
    if "--json" in sys.argv:
        print(json.dumps({"verdict": v, "accepted": acc, "rejected": rej, "seconds": round(total, 1),
                          "llm_calls": state.llm_calls}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
