"""Unpack a Claude Design bundle export (design/Casefile.html) into design/src/.

The export is a "__bundler" page:
  <script type="__bundler/manifest">      {uuid: {mime, compressed, data}}  data = base64, gzip if compressed
  <script type="__bundler/template">      the page HTML as a JSON string; resources referenced by uuid
  <script type="__bundler/ext_resources"> [{id: external URL, uuid}]  (React UMD from unpkg)
This writes every resource to design/src/res/<uuid>.<ext>, the template to design/src/index.html
(uuids replaced by the extracted file paths), and design/src/manifest.json describing them.

Usage: uv run python scripts/unpack_design.py [design/Casefile.html]
"""

from __future__ import annotations

import base64
import gzip
import json
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = {"text/javascript": ".js", "application/javascript": ".js", "text/css": ".css", "text/html": ".html",
       "image/svg+xml": ".svg", "font/woff2": ".woff2", "font/woff": ".woff", "font/ttf": ".ttf",
       "application/json": ".json", "image/png": ".png", "image/jpeg": ".jpg"}


def _block(html: str, kind: str) -> str | None:
    m = re.search(rf'<script type="__bundler/{kind}">(.*?)</script>', html, re.S)
    return m.group(1).strip() if m else None


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "design" / "Casefile.html"
    out = ROOT / "design" / "src"
    res_dir = out / "res"
    res_dir.mkdir(parents=True, exist_ok=True)
    html = src.read_text()

    manifest = json.loads(_block(html, "manifest") or "{}")
    ext = json.loads(_block(html, "ext_resources") or "[]")
    template = json.loads(_block(html, "template") or '""')

    index = {}
    for uuid, entry in manifest.items():
        raw = base64.b64decode(entry["data"])
        if entry.get("compressed"):
            raw = gzip.decompress(raw)
        mime = entry.get("mime", "application/octet-stream")
        suffix = EXT.get(mime) or mimetypes.guess_extension(mime) or ".bin"
        name = f"{uuid}{suffix}"
        (res_dir / name).write_bytes(raw)
        index[uuid] = {"file": f"res/{name}", "mime": mime, "bytes": len(raw)}

    for e in ext:
        index.setdefault(e["uuid"], {"file": e["id"], "mime": "external", "bytes": None})

    page = template
    for uuid, info in index.items():
        page = page.replace(uuid, info["file"])
    (out / "index.html").write_text(page)

    # Fonts: name each woff2 by family/style/subset and write the design's own @font-face CSS.
    fonts_dir = out / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    style = re.search(r"<style>(.*?)</style>", template, re.S).group(1)
    renamed: dict[str, str] = {}
    css_out = []
    for m in re.finditer(r"/\* ([\w-]+) \*/\s*@font-face \{(.*?)\}", style, re.S):
        subset, body = m.group(1), m.group(2)
        fam = re.search(r"font-family: '([^']+)'", body).group(1)
        sty = re.search(r"font-style: (\w+)", body).group(1)
        wt = re.search(r"font-weight: (\d+)", body).group(1)
        uuid = re.search(r'url\("?([0-9a-f-]{36})"?\)', body).group(1)
        name = renamed.setdefault(uuid, f"{fam.lower().replace(' ', '-')}-{sty}-{wt}-{subset}.woff2")
        (fonts_dir / name).write_bytes((res_dir / index[uuid]["file"].split("/")[-1]).read_bytes())
        css_out.append(f"/* {subset} */\n@font-face {{{body.replace(uuid, '/fonts/' + name)}}}")
    (out / "fonts.css").write_text("\n".join(css_out) + "\n")
    print(f"fonts: {len(renamed)} files, {len(css_out)} @font-face rules -> {fonts_dir}")
    (out / "manifest.json").write_text(json.dumps(index, indent=1) + "\n")
    print(f"unpacked {len(manifest)} resources + {len(ext)} external -> {out}")
    for uuid, info in sorted(index.items(), key=lambda kv: -(kv[1]["bytes"] or 0)):
        print(f"  {info['mime']:<26} {info['bytes'] or '-':>8}  {info['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
