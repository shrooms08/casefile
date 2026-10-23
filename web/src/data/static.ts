import type { DataSource, TraceDoc } from "./types";
import { replayDelay } from "./timing";

// Reads the exported JSON in web/public/demo/ (scripts/build_static_demo.py) and replays
// client-side with the server's timing rules. Needs no backend at all.
const ROOT = `${import.meta.env.BASE_URL}demo`;
const traces = new Map<string, Promise<TraceDoc>>();

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${ROOT}/${path}`);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return (await r.json()) as T;
}

function trace(id: string): Promise<TraceDoc> {
  if (!traces.has(id)) traces.set(id, getJson<TraceDoc>(`${id}/trace.json`));
  return traces.get(id)!;
}

export const staticSource: DataSource = {
  kind: "static",
  health: () => getJson("health.json"),
  cases: () => getJson("cases.json"),
  async caseDetail(id) {
    return getJson(`${id}/case.json`);
  },
  async trace(id, run) {
    const t = await trace(id);
    if (run && run !== t.run_id) throw new Error(`run ${run} is not in the static demo`);
    return t;
  },
  replay(id, opts, h) {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    trace(id).then((t) => {
      if (cancelled) return;
      const events = t.events.filter((e) => e.seq > opts.from);
      let prevTs = t.events.find((e) => e.seq === opts.from)?.ts ?? null;
      let i = 0;
      const step = () => {
        if (cancelled) return;
        if (i >= events.length) {
          h.onDone({ type: "done", case_id: id, run_id: t.run_id, summary: t.summary });
          return;
        }
        const e = events[i];
        timer = setTimeout(() => {
          if (cancelled) return;
          h.onEvent(e);
          prevTs = e.ts;
          i += 1;
          step();
        }, replayDelay(prevTs, e.ts, opts.speed) * 1000);
      };
      step();
    }, (err) => h.onError?.(String(err)));
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  },
  stream(_id, _run, h) {
    h.onError?.("Live streams need the local stack; this build replays recorded cases only.");
    return () => {};
  },
  async investigate() {
    throw new Error("Live investigations need the local stack. Watch a recorded case below.");
  },
  memory: () => getJson("memory.json"),
};
