"""query_case: the one tool agents get. Read-only SQL against this case's snapshot tables.

Rules enforced here (not by the prompt):
  - exactly one statement, and it must be a SELECT (or WITH ... SELECT)
  - no write/DDL keywords anywhere
  - every table it reads must be one of this case's CASEFILE_SNAP snapshot tables
    (agents may write the short name, e.g. `holders`, which is expanded)
  - goes through casefile.zetaris.run_sql, so it is serialized behind the Zetaris lock
  - row cap 200; the SQL is logged in the trace
"""

from __future__ import annotations

import re
from typing import Any

from casefile.agents.state import CaseState, Trace
from casefile.zetaris import ZetarisError, _has_multiple_statements, run_sql

ROW_CAP = 200
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|replace|cache|uncache|"
    r"refresh|export|run|load|set|use|call|exec|execute|msck|analyze|compile|register|materialize)\b", re.I)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w.]*)", re.I)


class QueryRejected(ValueError):
    pass


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def validate(state: CaseState, sql: str) -> str:
    """Return the SQL with short table names expanded, or raise QueryRejected."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryRejected("empty query")
    if _has_multiple_statements(sql):
        raise QueryRejected("exactly one statement, no semicolons")
    bare = _strip_literals(sql)
    if not re.match(r"^\s*(select|with)\b", bare, re.I):
        raise QueryRejected("only SELECT statements are allowed")
    bad = _FORBIDDEN.search(bare)
    if bad:
        raise QueryRejected(f"keyword not allowed: {bad.group(1)}")
    allowed_full = {t.lower(): t for t in state.snapshot_tables.values()}
    short = {k.lower(): v for k, v in state.snapshot_tables.items()}
    ctes = {m.group(1).lower() for m in re.finditer(r"\b(\w+)\s+as\s*\(", bare, re.I)}

    def expand(m: re.Match) -> str:
        name = m.group(1)
        low = name.lower()
        if low in allowed_full or low in ctes:
            return m.group(0)
        if low in short:
            return m.group(0)[: m.start(1) - m.start(0)] + short[low]
        raise QueryRejected(f"table not allowed: {name} (use one of: {', '.join(sorted(short))})")

    out = _TABLE_REF.sub(expand, sql)
    if not _TABLE_REF.search(_strip_literals(out)):
        raise QueryRejected("query reads no table")
    return out


def query_case(state: CaseState, trace: Trace, agent: str, sql: str) -> dict[str, Any]:
    try:
        final = validate(state, sql)
    except QueryRejected as e:
        trace.log("query_rejected", agent, {"error": str(e)}, sql=sql)
        return {"ok": False, "error": str(e)}
    try:
        rows = run_sql(final, limit=ROW_CAP)
    except ZetarisError as e:
        trace.log("query_error", agent, {"error": str(e)[:500]}, sql=final)
        return {"ok": False, "error": str(e)[:500]}
    trace.log("query", agent, {"rows": len(rows), "sample": rows[:5]}, sql=final,
              input_summary=f"{agent} ran query_case")
    return {"ok": True, "rows": rows}
