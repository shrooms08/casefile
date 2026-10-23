"""`casefile` command line.

  uv run casefile serve [--replay] [--host 127.0.0.1] [--port 8000]
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="casefile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the Casefile API")
    s.add_argument("--replay", action="store_true", help="replay recorded demo cases only (no Zetaris/Nightshift)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    if args.cmd == "serve":
        import uvicorn

        from casefile.server.app import create_app
        print(f"Casefile API ({'replay' if args.replay else 'live'} mode) on http://{args.host}:{args.port}")
        uvicorn.run(create_app(replay=args.replay), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
