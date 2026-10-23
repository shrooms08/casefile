"""Check the Meterless Nightshift provider.

Lists discovered models, makes one tiny call per role (printing routed_model and receipt_id),
and runs the provider-contract done checks: a wrong token shows "unauthorized", Auto Detect
finds the runtime, and a plain text request on meterless/auto returns a string.

Usage: uv run python scripts/check_nightshift.py
"""

import os

from casefile import llm


def main() -> int:
    ok = True
    base = llm._base_url()
    print(f"provider {llm.PROVIDER_NAME} ({llm.PROVIDER_ID}) at {base}")
    print(f"status: {llm.status()}")

    try:
        models = llm.discover_models()
    except llm.MeterlessError as e:
        print(f"FAILED discovery: {e}")
        return 1
    print(f"discovered {len(models)} models:")
    for m in models:
        print(f"  {m}")

    for role in ("fast", "deep"):
        print(f"\nrole={role} -> requested {llm.model_for_role(role)}")
        try:
            r = llm.chat([{"role": "user", "content": "Reply with the single word: ready"}],
                         role=role, case_id="_check")
        except llm.MeterlessError as e:
            print(f"  FAILED: {e}")
            ok = False
            continue
        print(f"  content      : {r.content.strip()[:80]!r}")
        print(f"  routed_model : {r.routed_model}")
        print(f"  receipt_id   : {r.receipt_id}")
        print(f"  provider     : {r.provider}   latency {r.latency_ms} ms   tokens {r.tokens}")
        print(f"  cross_check  : {r.cross_check}")
        if r.routing_note:
            print(f"  NOTE         : {r.routing_note}")
        print(f"  receipt keys : body={sorted(r.receipt['response'])} "
              f"headers={sorted(r.receipt['response_headers'])}")

    print("\ncontract checks")
    real = os.environ.get("METERLESS_RUNTIME_TOKEN")
    os.environ["METERLESS_RUNTIME_TOKEN"] = "wrong-token-for-check"
    wrong = llm.status()
    os.environ["METERLESS_RUNTIME_TOKEN"] = real or ""
    print(f"  wrong token -> {wrong}  {'PASS' if wrong == 'unauthorized' else 'FAIL'}")
    ok &= wrong == "unauthorized"

    saved = os.environ.get("METERLESS_BASE_URL")
    found = llm.auto_detect()
    if saved is not None:
        os.environ["METERLESS_BASE_URL"] = saved
    print(f"  auto detect -> {found}  {'PASS' if found else 'FAIL'}")
    ok &= bool(found)

    os.environ["CASEFILE_FAST_MODEL"] = "meterless/auto"
    try:
        r = llm.chat("Say hi in two words.", role="fast", case_id="_check")
        plain = isinstance(r.content, str) and bool(r.content.strip())
        print(f"  plain text on meterless/auto -> {r.content.strip()[:60]!r} "
              f"(routed {r.routed_model})  {'PASS' if plain else 'FAIL'}")
    except llm.MeterlessError as e:
        plain = False
        print(f"  plain text on meterless/auto -> FAILED: {e}")
    ok &= plain

    for u in ("127.0.0.1:8088", "http://127.0.0.1:8088/v1/v1", "http://127.0.0.1:8088/v1/chat/completions",
              "127.0.0.1:8088/healthz", "http://localhost:8088/v1/models"):
        print(f"  normalise {u!r:45} -> {llm.normalise_base_url(u)}")

    print("\nNightshift OK" if ok else "\nNightshift check had failures")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
