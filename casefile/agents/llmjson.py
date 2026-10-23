"""One LLM step that must return JSON: call, parse, validate, retry once.

- invalid JSON or a failed schema check: one retry with the error appended
- transient Nightshift failures (HTTP 499 abort, 502 empty response, timeouts): up to three retries with backoff
Every attempt is counted on the state and written to the trace with its receipt id.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from casefile import llm
from casefile.agents.state import CaseState, Trace

Validator = Callable[[Any], list[str]]


class StepFailed(RuntimeError):
    pass


def parse_json(text: str) -> Any:
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        a, b = t.find(open_c), t.rfind(close_c)
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except ValueError:
                continue
    raise ValueError("no JSON object found in the reply")


def _transient(e: llm.MeterlessError) -> bool:
    return e.http_status in (499, 502, 503, 504) or e.status == "offline"


def call_json(state: CaseState, trace: Trace, *, agent: str, step: str, role: str,
              system: str, user: str, validate: Validator, input_summary: str) -> Any:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_err = ""
    attempt, transient_left, invalid_left = 0, 3, 1
    backoff = (3, 10, 20)
    while True:
        attempt += 1
        try:
            r = llm.chat(messages, role=role, case_id=state.case_id, json_mode=True, run_id=state.run_id)
        except llm.MeterlessError as e:
            state.llm_calls += 1
            trace.log(f"{step}_error", agent, {"attempt": attempt, "error": str(e)[:400]}, input_summary=input_summary)
            if _transient(e) and transient_left > 0:
                time.sleep(backoff[3 - transient_left])
                transient_left -= 1
                continue
            if _transient(e) and role == "deep":
                # Deep model kept getting cut off (Nightshift's 45 s first-token limit): one try on fast.
                trace.log(f"{step}_fallback", agent, {"from": "deep", "to": "fast", "reason": str(e)[:200]},
                          input_summary=input_summary)
                role, transient_left = "fast", 1
                continue
            raise StepFailed(f"{agent} {step}: {e}") from None
        state.llm_calls += 1
        if r.routed_model:
            state.models.add(r.routed_model)
        try:
            data = parse_json(r.content)
            errors = validate(data)
        except ValueError as e:
            data, errors = None, [str(e)]
        if not errors:
            trace.log(step, agent, data, model=r.routed_model, receipt_id=r.receipt_id,
                      input_summary=input_summary)
            return data
        last_err = "; ".join(errors)[:600]
        trace.log(f"{step}_invalid", agent, {"attempt": attempt, "errors": errors[:8], "raw": r.content[:600]},
                  model=r.routed_model, receipt_id=r.receipt_id, input_summary=input_summary)
        if invalid_left == 0:
            break
        invalid_left -= 1
        messages = messages[:2] + [
            {"role": "assistant", "content": r.content[:4000]},
            {"role": "user", "content": f"That reply was rejected: {last_err}. Reply again with ONLY valid JSON "
                                        f"in the required shape."},
        ]
    raise StepFailed(f"{agent} {step}: invalid output after retry: {last_err}")
