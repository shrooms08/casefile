"""Minimal Zetaris REST client: run one Lightning SQL statement, get rows back.

Request/response shape is from the Zetaris OpenAPI spec (operation RunSql):
  POST {ZETARIS_REST_URL}/sql-editor/sqls/run
  body     {"queryId": uuid, "sql": str, "source": "SqlEditor", "limit": int}
  200      {"headers": [str], "data": [[str]], "total": int, "timeUsed": int}
  error    {"msg": str}  (400 may be text/plain)

Credentials come from .env via python-dotenv and are never logged.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULT_REST_URL = "http://localhost:8888/api/v1.0"
DEFAULT_LIMIT = 1000
TIMEOUT_S = 300


class ZetarisError(RuntimeError):
    """A Zetaris request failed. The message never contains credentials."""

    def __init__(self, message: str, status: int | None = None, statement: str | None = None):
        super().__init__(message)
        self.status = status
        self.statement = statement

    @property
    def already_exists(self) -> bool:
        return bool(re.search(r"already exist", str(self), re.I))


def _config() -> tuple[str, str, str]:
    base = os.environ.get("ZETARIS_REST_URL", DEFAULT_REST_URL).rstrip("/")
    if ":8889" in base:
        raise ZetarisError("ZETARIS_REST_URL points at port 8889, which must not be used.")
    org = os.environ.get("ZETARIS_ORG_ID", "1")
    key = os.environ.get("ZETARIS_API_KEY", "")
    if not key or key.startswith("your-"):
        raise ZetarisError("ZETARIS_API_KEY is not set in .env.")
    return base, org, key


def _has_multiple_statements(sql: str) -> bool:
    """True if a ';' appears outside quotes and comments (a trailing one counts too,
    since Zetaris wants statements without a trailing semicolon)."""
    i, n, quote = 0, len(sql), None
    while i < n:
        c = sql[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
        elif sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                i += 1
            continue
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        elif c == ";":
            return True
        i += 1
    return False


def _scrub(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    text = " ".join(text.split())
    return text if len(text) <= 800 else text[:800] + "..."


def run_sql(statement: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Run exactly one Lightning SQL statement and return rows as dicts.

    Values come back as Zetaris returns them (strings, or None for SQL NULL).
    DDL statements usually return an empty list.
    """
    sql = statement.strip()
    if not sql:
        raise ZetarisError("Empty SQL statement.")
    if _has_multiple_statements(sql):
        raise ZetarisError("run_sql takes exactly one statement with no semicolons.")

    base, org, key = _config()
    try:
        resp = requests.post(
            f"{base}/sql-editor/sqls/run",
            json={"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit},
            headers={
                "Authorization": f"Bearer {key}",
                "X-Org-ID": org,
                "X-Request-ID": str(uuid.uuid4()),
            },
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as e:
        raise ZetarisError(f"Cannot reach Zetaris at {base}: {type(e).__name__}", statement=sql) from None

    if resp.status_code != 200:
        try:
            msg = resp.json().get("msg") or resp.text
        except ValueError:
            msg = resp.text
        raise ZetarisError(
            f"Zetaris HTTP {resp.status_code}: {_scrub(str(msg), key)}",
            status=resp.status_code,
            statement=sql,
        )

    body = resp.json() if resp.content else {}
    if not isinstance(body, dict):
        return []
    headers = body.get("headers") or []
    data = body.get("data") or []
    return [dict(zip(headers, row)) for row in data]
