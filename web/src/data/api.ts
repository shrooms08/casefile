import type { DataSource, DoneMessage, StreamHandlers, TraceEvent } from "./types";
import { BusyError } from "./types";

// Talks to the FastAPI server (same origin, or proxied to :8000 by `npm run dev`).
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

function sse(path: string, h: StreamHandlers): () => void {
  const es = new EventSource(BASE + path);
  let closed = false;
  es.onmessage = (m) => {
    let data: TraceEvent | DoneMessage;
    try {
      data = JSON.parse(m.data);
    } catch {
      return;
    }
    if ((data as DoneMessage).type === "done") {
      closed = true;
      es.close();
      h.onDone(data as DoneMessage);
    } else {
      h.onEvent(data as TraceEvent);
    }
  };
  es.onerror = () => {
    if (closed) return;
    closed = true;
    es.close();
    h.onError?.("The event stream was interrupted.");
  };
  return () => {
    closed = true;
    es.close();
  };
}

export const apiSource: DataSource = {
  kind: "api",
  health: () => getJson("/api/health"),
  cases: () => getJson("/api/cases"),
  caseDetail: (id, run) => getJson(`/api/cases/${encodeURIComponent(id)}${run ? `?run=${encodeURIComponent(run)}` : ""}`),
  trace: (id, run) => getJson(`/api/cases/${encodeURIComponent(id)}/trace${run ? `?run=${encodeURIComponent(run)}` : ""}`),
  replay: (id, o, h) =>
    sse(`/api/cases/${encodeURIComponent(id)}/replay?speed=${o.speed}&from=${o.from}${o.run ? `&run=${encodeURIComponent(o.run)}` : ""}`, h),
  stream: (id, run, h) => sse(`/api/cases/${encodeURIComponent(id)}/stream?run=${encodeURIComponent(run)}`, h),
  async investigate(mint) {
    const r = await fetch(BASE + "/api/investigate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ mint }),
    });
    const body = await r.json().catch(() => ({}));
    if (r.status === 409) throw new BusyError(body.running);
    if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
    return body;
  },
  memory: () => getJson("/api/memory"),
};
