"""Measure thinking cost on the fast role: same small prompt, one variant at a time.

Usage: uv run python scripts/perf_thinking.py [variant ...]
Variants: baseline, no_think, detailed_off, template_kwargs, max800_json, and combos joined by '+'.
Each prompt carries a nonce so Nightshift's exact-match cache can't answer it.
"""

import json
import sys
import time
import uuid

from casefile import llm

EVIDENCE = {
    "summary": {"symbol": "Bonk", "score_normalised": 7, "rugged": False, "total_holders": 2096691,
                "mint_authority": None, "freeze_authority": None, "graph_insiders_detected": 0},
    "top_pair": {"liquidity_usd": 321903.26, "price_change_24h": -2.1, "pair_age_days": 1040},
    "top_holders": [{"pct": 8.83, "label": None}, {"pct": 6.79, "label": None}],
    "risks": [{"name": "Mutable metadata", "level": "warn"}],
}
TASK = ("Return JSON {\"lines\": [three short strings]}: what does this evidence suggest about this token, "
        "citing the specific field for each claim.")

VARIANTS = {
    "baseline": {},
    "no_think": {"system": "/no_think"},
    "detailed_off": {"system": "detailed thinking off"},
    "template_kwargs": {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
    "max800_json": {"max_tokens": 800, "json_mode": True},
    "max2500": {"max_tokens": 2500},
    "json": {"json_mode": True},
    "brief": {"system": "Think briefly. Reply with ONLY one JSON object."},
}
ROLE = "fast"


def build(name: str) -> dict:
    opts: dict = {}
    for part in name.split("+"):
        v = VARIANTS[part]
        if "system" in v:
            opts["system"] = (opts.get("system", "") + "\n" + v["system"]).strip()
        for k in ("extra_body", "max_tokens", "json_mode"):
            if k in v:
                opts[k] = v[k]
    return opts


def run(name: str) -> dict:
    o = build(name)
    msgs = []
    if o.get("system"):
        msgs.append({"role": "system", "content": o["system"]})
    msgs.append({"role": "user", "content": f"{TASK}\nEVIDENCE: {json.dumps(EVIDENCE)}\n(nonce {uuid.uuid4().hex[:8]})"})
    t = time.time()
    try:
        r = llm.chat(msgs, role=ROLE, case_id="_perf", json_mode=o.get("json_mode", False),
                     max_tokens=o.get("max_tokens"), extra_body=o.get("extra_body"))
    except llm.MeterlessError as e:
        return {"variant": name, "error": str(e), "seconds": round(time.time() - t, 1)}
    try:
        lines = json.loads(r.content).get("lines")
        valid = isinstance(lines, list) and len(lines) == 3
    except (ValueError, AttributeError):
        valid = False
    meta = r.receipt["response"].get("meterless") or {}
    return {
        "variant": name,
        "role": ROLE,
        "seconds": round(r.latency_ms / 1000, 1),
        "completion_tokens": r.tokens.get("completion_tokens"),
        "prompt_tokens": r.tokens.get("prompt_tokens"),
        "valid_json_3_lines": valid,
        "routed_model": r.routed_model,
        "phases": [(p.get("phase"), p.get("model", "").split("/")[-1], p.get("tokensOut")) for p in meta.get("phases") or []],
        "from_cache": meta.get("from_cache"),
        "receipt_id": r.receipt_id,
        "content": r.content[:160],
    }


def main() -> int:
    global ROLE
    args = sys.argv[1:]
    if args[:1] == ["--deep"]:
        ROLE, args = "deep", args[1:]
    names = args or list(VARIANTS)
    results = []
    for n in names:  # one at a time, never in parallel
        res = run(n)
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
