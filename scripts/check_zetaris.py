"""Smoke test for the Zetaris REST connection."""

from casefile.zetaris import ZetarisError, run_sql


def main() -> int:
    try:
        for sql in ("SELECT 1 AS one", "SHOW LIGHTNING DATABASES"):
            rows = run_sql(sql)
            print(f"> {sql}  ({len(rows)} rows)")
            for row in rows:
                print("   ", row)
    except ZetarisError as e:
        print(f"FAILED: {e}")
        return 1
    print("Zetaris connection OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
