"""Meterless Runtime (Nightshift) as Casefile's OpenAI-compatible AI provider.

Contract: Meterless Runtime 1.4, provider contract v4.
  - provider id "meterless", name "Meterless Runtime", default base http://127.0.0.1:8088/v1
  - Authorization: Bearer <token> on every call; "rt-local" is rejected
  - meterless-app: casefile on every request, meterless-scope: user on chat
  - GET /v1/models decides status: 401/403 unauthorized, 200 with meterless ids online,
    anything else offline (GET /healthz only proves the process is up)
  - 180 s timeout, since a model load can take minutes

Public API:
  chat(messages, role="fast"|"deep", json_mode=False, case_id=None, reasoning_effort=None)
  status(), discover_models(), auto_detect(), normalise_base_url(), parse_connect_link()

Every chat call appends its full receipt to runs/<case_id>/receipts.jsonl (gitignored).
The token is read from METERLESS_RUNTIME_TOKEN (or <stateDir>/proxy-token) and is never
logged, printed or written to a receipt.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROVIDER_ID = "meterless"
PROVIDER_NAME = "Meterless Runtime"
DEFAULT_BASE_URL = "http://127.0.0.1:8088/v1"
TOKEN_KEY = "meterless_runtime_token"
APP_ID = "casefile"
TIMEOUT_S = 180
REJECTED_TOKENS = {"rt-local"}
RUNS_DIR = ROOT / "runs"

DETECT_PORTS = (8088, 8090, 8787, 11434)
DETECT_HOSTS = ("127.0.0.1", "localhost", "[::1]")

log = logging.getLogger("casefile.llm")


class MeterlessError(RuntimeError):
    """A Meterless call failed. The message never contains the token."""

    def __init__(self, message: str, status: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.status = status
        self.http_status = http_status


# --- configuration --------------------------------------------------------------


def normalise_base_url(url: str | None) -> str:
    """Accept a pasted URL with or without scheme, /v1, /v1/chat/completions, /v1/models
    or /healthz, and return <scheme>://<host>/v1. Never produces /v1/v1."""
    url = (url or "").strip() or DEFAULT_BASE_URL
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/models", "/healthz"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    while path.endswith("/v1"):
        path = path[:-3]
    return f"{parts.scheme}://{parts.netloc}{path}/v1"


def parse_connect_link(link: str) -> tuple[str, str]:
    """http://<host>:<port>/connect#k=<key> -> (base_url, key). Never log the result."""
    parts = urlsplit(link.strip())
    m = re.search(r"(?:^|&)k=([^&]+)", parts.fragment or "")
    if not parts.netloc or not m:
        raise MeterlessError("Not a Meterless connect link (expected http://host:port/connect#k=...).")
    return f"{parts.scheme or 'http'}://{parts.netloc}/v1", m.group(1)


def _state_dir_token() -> str:
    state = os.environ.get("METERLESS_STATE_DIR")
    if not state:
        return ""
    try:
        return (Path(state).expanduser() / "proxy-token").read_text().strip()
    except OSError:
        return ""


def _token() -> str:
    token = (os.environ.get("METERLESS_RUNTIME_TOKEN") or "").strip() or _state_dir_token()
    if not token or token.startswith("your-"):
        raise MeterlessError("METERLESS_RUNTIME_TOKEN is not set in .env.", status="unauthorized")
    if token in REJECTED_TOKENS:
        raise MeterlessError("The placeholder token rt-local is rejected; paste the real runtime token.",
                             status="unauthorized")
    return token


def _base_url() -> str:
    link = os.environ.get("METERLESS_CONNECT_LINK")
    if link:
        return parse_connect_link(link)[0]
    return normalise_base_url(os.environ.get("METERLESS_BASE_URL"))


def _headers(token: str, chat: bool = False) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}", "meterless-app": APP_ID}
    if chat:
        h["meterless-scope"] = "user"
    return h


def _scrub(text: str, token: str) -> str:
    if token:
        text = text.replace(token, "***")
    text = " ".join(str(text).split())
    return text if len(text) <= 600 else text[:600] + "..."


# --- status and discovery -------------------------------------------------------


def _probe(base: str, token: str, timeout: float = 10) -> tuple[str, list[dict]]:
    """Return (status, models) where status is online / unauthorized / offline."""
    try:
        r = requests.get(f"{base}/models", headers=_headers(token), timeout=timeout)
    except requests.RequestException:
        return "offline", []
    if r.status_code in (401, 403):
        return "unauthorized", []
    if r.status_code != 200:
        return "offline", []
    try:
        models = r.json().get("data") or []
    except (ValueError, AttributeError):
        return "offline", []
    if not any(str(m.get("id", "")).startswith("meterless/") for m in models):
        return "offline", models
    return "online", models


def status() -> str:
    try:
        token = _token()
    except MeterlessError:
        token = ""
    return _probe(_base_url(), token)[0]


def auto_detect() -> str | None:
    """Try the standard ports on 127.0.0.1, localhost and [::1]; return the first base URL
    that is online or unauthorized, and save it to the process env (not to disk)."""
    try:
        token = _token()
    except MeterlessError:
        token = ""
    for host in DETECT_HOSTS:
        for port in DETECT_PORTS:
            base = f"http://{host}:{port}/v1"
            st, _ = _probe(base, token, timeout=2)
            if st in ("online", "unauthorized"):
                os.environ["METERLESS_BASE_URL"] = base
                return base
    return None


_models_lock = threading.Lock()
_models_cache: list[str] | None = None


def discover_models(refresh: bool = False) -> list[str]:
    """All model ids from GET /v1/models, including any meterless/* id we don't recognise."""
    global _models_cache
    with _models_lock:
        if _models_cache is not None and not refresh:
            return _models_cache
        token = _token()
        st, models = _probe(_base_url(), token)
        if st == "unauthorized":
            raise MeterlessError("Meterless rejected the runtime token (401/403).", status=st)
        if st == "offline":
            raise MeterlessError(f"Meterless Runtime is offline at {_base_url()}.", status=st)
        _models_cache = [str(m.get("id")) for m in models if m.get("id")]
        return _models_cache


def model_for_role(role: str) -> str:
    """CASEFILE_FAST_MODEL / CASEFILE_DEEP_MODEL if the runtime lists them. Deep falls back
    to fast; fast falls back to METERLESS_MODEL (default meterless/auto)."""
    if role not in ("fast", "deep"):
        raise ValueError(f"role must be 'fast' or 'deep', not {role!r}")
    available = set(discover_models())
    fallback = os.environ.get("METERLESS_MODEL") or "meterless/auto"
    fast = os.environ.get("CASEFILE_FAST_MODEL") or fallback
    deep = os.environ.get("CASEFILE_DEEP_MODEL") or fast
    if role == "deep":
        if deep in available:
            return deep
        log.warning("Deep model %s is not offered by Meterless; falling back to the fast model.", deep)
        role = "fast"
    if fast in available:
        return fast
    log.warning("Fast model %s is not offered by Meterless; falling back to %s.", fast, fallback)
    return fallback


# --- chat -----------------------------------------------------------------------


@dataclass
class ChatResult:
    content: str
    routed_model: str | None
    receipt_id: str | None
    provider: str
    latency_ms: int
    tokens: dict[str, Any]
    cross_check: Any
    requested_model: str
    role: str
    routing_note: str | None = None
    receipt: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("receipt")
        return d


def _meterless_headers(resp: requests.Response) -> dict[str, str]:
    return {k.lower(): v for k, v in resp.headers.items()
            if k.lower().startswith(("meterless", "x-meterless"))}


def _persist(case_id: str | None, record: dict[str, Any]) -> None:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", case_id or "_adhoc")
    d = RUNS_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    with (d / "receipts.jsonl").open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def chat(
    messages: list[dict[str, Any]] | str,
    role: str = "fast",
    json_mode: bool = False,
    case_id: str | None = None,
    reasoning_effort: str | None = None,
) -> ChatResult:
    """One chat completion through Meterless. A plain string becomes one user message.
    reasoning_effort ("low" / "medium" / "high") is passed through to models that support it."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    token = _token()
    base = _base_url()
    model = model_for_role(role)
    body: dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    call_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        resp = requests.post(f"{base}/chat/completions", json=body,
                             headers=_headers(token, chat=True), timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise MeterlessError(f"Cannot reach Meterless at {base}: {type(e).__name__}",
                             status="offline") from None
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code in (401, 403):
        raise MeterlessError("Meterless rejected the runtime token (401/403).",
                             status="unauthorized", http_status=resp.status_code)
    if resp.status_code != 200:
        raise MeterlessError(f"Meterless HTTP {resp.status_code}: {_scrub(resp.text, token)}",
                             http_status=resp.status_code)
    try:
        data = resp.json()
    except ValueError:
        raise MeterlessError(f"Meterless returned non-JSON: {_scrub(resp.text, token)}") from None

    mheaders = _meterless_headers(resp)
    meta = data.get("meterless") or {}
    rcpt = meta.get("receipt") or {}
    cross = data.get("meterless_cross_check") or rcpt.get("cross_check") or {}
    route = meta.get("winning_route") or rcpt.get("winning_route") or {}
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    if isinstance(content, list):  # tolerate content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))

    routed = meta.get("routed_model") or route.get("model") or data.get("model")
    bound_mode = meta.get("provider_model") or rcpt.get("requested_mode")
    note = None
    if routed and routed != model and not model.startswith("meterless/"):
        # A bound app (Nightshift > Apps) routes by its pressed mode, not the client's model.
        note = (f"requested {model} but Nightshift routed to {routed} "
                f"(app '{APP_ID}' is bound to {bound_mode} in Nightshift > Apps)")
        log.warning(note)

    result = ChatResult(
        content=content,
        routed_model=routed,
        receipt_id=meta.get("receipt_id") or rcpt.get("receipt_id") or mheaders.get("meterless-receipt-id"),
        provider=route.get("provider") or PROVIDER_ID,
        latency_ms=latency_ms,
        tokens=data.get("usage") or {},
        cross_check=cross.get("status") if isinstance(cross, dict) else cross,
        requested_model=model,
        role=role,
        routing_note=note,
    )
    record = {
        "call_id": call_id,
        "case_id": case_id,
        "at": started.isoformat(timespec="milliseconds"),
        "provider": PROVIDER_ID,
        "base_url": base,
        "role": role,
        "requested_model": model,
        "json_mode": json_mode,
        "reasoning_effort": reasoning_effort,
        "latency_ms": latency_ms,
        "routed_model": result.routed_model,
        "receipt_id": result.receipt_id,
        "cross_check": result.cross_check,
        "routing_note": note,
        "bound_mode": bound_mode,
        "tokens": result.tokens,
        "request": {"messages": messages},
        "response_headers": mheaders,
        "response": data,
    }
    result.receipt = record
    _persist(case_id, record)
    return result
