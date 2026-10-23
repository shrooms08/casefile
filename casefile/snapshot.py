"""Evidence snapshots: freeze each case view once, inside Zetaris.

A REST table refetches its API on every query (the BONK RugCheck report is 2.5 MB), so a
live case file takes 25-35 s. open_case therefore freezes each view once:

  1. RUN EXPORT TO STORAGE runs the view (Zetaris fetches and shapes the data) and writes
     the result, plus a captured_at column, as Parquet to Zetaris' local file storage.
  2. CREATE LIGHTNING FILESTORE TABLE CASEFILE_SNAP.<cid>_<view>_snap reads that Parquet.

Later case-file reads query the snapshot tables (about 1 s each). Nothing is overwritten:
each export goes to a new timestamped folder (saveMode errorifexists) and an existing
snapshot table is kept as is.
Snapshot paths are recorded in cases.json; the approach is documented in fixtures/SOURCES.md.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from casefile.zetaris import ZetarisError, run_sql

if TYPE_CHECKING:
    from casefile.sources import Case

SNAP_DB = "CASEFILE_SNAP"
# Inside the Zetaris driver container: ZETARIS_LOCAL_FILE_SYTEM_ROOT_PATH + /casefile_snap
SNAP_ROOT = os.environ.get("CASEFILE_SNAP_ROOT",
                           "file:///home/zetaris/customer-data/shared/casefile_snap")
_NO_OPTIONS = base64.b64encode(b"{}").decode()


def snap_table(cid: str, key: str) -> str:
    return f"{cid}_{key}_snap"


def snapshot_select(view: str) -> str:
    """The exact SQL whose result is frozen for one view."""
    return f"SELECT *, current_timestamp() AS captured_at FROM {view}"


def _export_sql(select: str, path: str) -> str:
    # The Lightning parser rejects '' escapes inside the query string; use "..." literals.
    if "'" in select:
        raise ZetarisError("Snapshot SQL must not contain single quotes.")
    return (f"RUN EXPORT TO STORAGE (query = '{select}', path = '{path}', format = 'parquet', "
            f"saveMode = 'errorifexists', optionsBase64 = '{_NO_OPTIONS}')")


def _ensure_db() -> None:
    if SNAP_DB in {r["name"].upper() for r in run_sql("SHOW LIGHTNING DATABASES")}:
        return
    try:
        run_sql(f'CREATE LIGHTNING DATABASE {SNAP_DB} DESCRIBE BY "Casefile frozen evidence snapshots"')
    except ZetarisError as e:
        if not e.already_exists:
            raise


# Top holders with a label from RugCheck knownAccounts (matched on owner wallet, then token
# account) or lockers (matched on token account). Unlabelled holders keep label NULL. Built
# from the snapshot tables: on the live views this self-joins one REST table and fails.
LABELLED_HOLDERS = (
    "SELECT h.*, COALESCE(ko.name, kt.name, lk.label) AS label, "
    "COALESCE(ko.type, kt.type, lk.label_type) AS label_type "
    "FROM {h} h "
    "LEFT JOIN (SELECT address, max(name) AS name, max(type) AS type FROM {k} GROUP BY address) ko "
    "ON ko.address = h.owner "
    "LEFT JOIN (SELECT address, max(name) AS name, max(type) AS type FROM {k} GROUP BY address) kt "
    "ON kt.address = h.token_account "
    'LEFT JOIN (SELECT token_account, "locker" AS label, max(type) AS label_type FROM {l} '
    "GROUP BY token_account) lk ON lk.token_account = h.token_account"
)
# Same, for a token with no lockers (a zero-row snapshot can't be read).
LABELLED_HOLDERS_NO_LOCKERS = (
    LABELLED_HOLDERS.split(" LEFT JOIN (SELECT token_account")[0]
    .replace("COALESCE(ko.name, kt.name, lk.label)", "COALESCE(ko.name, kt.name)")
    .replace("COALESCE(ko.type, kt.type, lk.label_type)", "COALESCE(ko.type, kt.type)")
)


def _count(table: str) -> int:
    """Rows in a snapshot table; a zero-row export has no Parquet schema and can't be read."""
    try:
        return int(run_sql(f"SELECT count(*) AS n FROM {table}")[0]["n"])
    except ZetarisError as e:
        if re.search(r"infer schema|UNABLE_TO_INFER_SCHEMA", str(e), re.I):
            return 0
        raise


def _freeze(select: str, table: str, source: str) -> dict:
    # A fresh folder per attempt, so an interrupted export can never be registered.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = f"{SNAP_ROOT}/{table}/{stamp}"
    run_sql(_export_sql(select, path))
    try:
        run_sql(f'CREATE LIGHTNING FILESTORE TABLE {table} FROM {SNAP_DB} FORMAT PARQUET '
                f'OPTIONS (PATH "{path}")')
    except ZetarisError as e:
        if not e.already_exists:
            raise
    full = f"{SNAP_DB.lower()}.{table}"
    return {"table": full, "path": path, "view": source, "sql": select, "rows": _count(full)}


def ensure_snapshots(case: "Case", log: Callable[..., None] = lambda *a, **k: None) -> dict[str, dict]:
    """Freeze every view of the case that has no snapshot yet, then the labelled holders.
    Returns key -> {table, path, view, sql, rows}."""
    _ensure_db()
    present = {r["name"].lower() for r in run_sql(f"SHOW LIGHTNING TABLES {SNAP_DB}")}
    out: dict[str, dict] = {}
    errors: dict[str, str] = {}

    def ensure(key: str, select: str, source: str) -> None:
        table = snap_table(case.cid, key)
        full = f"{SNAP_DB.lower()}.{table}"
        prior = case.snapshots.get(key) or {}
        try:
            if table in present:
                rows = prior["rows"] if "rows" in prior else _count(full)
                out[key] = {**prior, "table": full, "view": source, "sql": select, "rows": rows}
                log(f"  snapshot {full}: exists ({rows} rows)")
            else:
                out[key] = _freeze(select, table, source)
                log(f"  snapshot {full}: created ({out[key]['rows']} rows)")
        except ZetarisError as e:
            errors[key] = str(e)
            log(f"  snapshot {key} failed: {e}")

    # One export at a time: 8 parallel RUN EXPORT jobs wedged the local Zetaris driver
    # (Spark stopped at "Starting job: save" and port 10000 stopped answering queries).
    for key, view in case.views.items():
        ensure(key, snapshot_select(view), view)

    if all((out.get(k) or {}).get("rows") for k in ("holders", "known_accounts")):
        with_lockers = bool((out.get("lockers") or {}).get("rows"))
        template = LABELLED_HOLDERS if with_lockers else LABELLED_HOLDERS_NO_LOCKERS
        sql = template.format(h=out["holders"]["table"], k=out["known_accounts"]["table"],
                              l=(out.get("lockers") or {}).get("table"))
        parts = ["holders", "known_accounts"] + (["lockers"] if with_lockers else [])
        ensure("holders_labelled", sql, "+".join(out[k]["table"] for k in parts))

    if errors and not out:
        raise ZetarisError("; ".join(f"{k}: {v}" for k, v in errors.items()))
    return out
