import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { data, replayDelay, tsSeconds } from "../data";
import type { CaseDetail, TraceEvent } from "../data";
import { useApp } from "../App";
import { LANES, laneState, pendingReviews, reduceBoard } from "../board/reducer";
import type { Board, ClaimCard, LaneKey } from "../board/reducer";
import { sx } from "../lib/sx";
import { BLUE, GREEN, OCH_TAB, RED, RED_TAB, ROT, clock, date, labelColor, labelText, modelName, modelShort, timeUtc } from "../lib/format";
import { Loading, copyText } from "./common";
import EvidencePocket from "./EvidencePocket";

const LANE_DEFS: { key: LaneKey; name: string; tab: string }[] = [
  { key: "holders", name: "Holders", tab: BLUE },
  { key: "liquidity", name: "Liquidity and market", tab: OCH_TAB },
  { key: "deployer", name: "Deployer and insiders", tab: RED_TAB },
];
const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const inAnim = reduced ? "none" : "cfIn 300ms ease-out both";
const stampAnim = reduced ? "none" : "cfStamp 260ms cubic-bezier(.3,1.4,.5,1) both";
const sheetAnim = reduced ? "none" : "cfSheet 380ms ease-out both";
const pulse = reduced ? "none" : "cfPulse 1.1s ease-in-out infinite";
const stampColor = (s: string) => (s === "ACCEPTED" ? GREEN : RED);

/** Wall-clock replay of a recorded run (server SSE or client timer, same timing rules). */
function useReplay(caseId: string, run: string | undefined, all: TraceEvent[] | null, enabled: boolean) {
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [key, setKey] = useState(0);              // bump to reconnect from `shown`
  const [, tick] = useState(0);
  const lastWall = useRef(performance.now());
  const shownRef = useRef(0);
  shownRef.current = shown;
  const total = all?.length ?? 0;

  useEffect(() => { if (enabled && all) { setShown(0); setPlaying(true); lastWall.current = performance.now(); } }, [enabled, all]);
  useEffect(() => {
    if (!enabled || !all || !playing) return;
    if (shownRef.current >= total) { setPlaying(false); return; }
    lastWall.current = performance.now();
    return data.replay(caseId, { speed, from: shownRef.current, run }, {
      onEvent: (e) => { lastWall.current = performance.now(); setShown(e.seq); },
      onDone: () => { setShown(total); setPlaying(false); },
      onError: () => setPlaying(false),
    });
  }, [enabled, all, playing, speed, key, caseId, run, total]);
  useEffect(() => {
    if (!playing) return;
    const iv = setInterval(() => tick((n) => n + 1), 100);
    return () => clearInterval(iv);
  }, [playing]);

  const t0 = tsSeconds(all?.[0]?.ts) ?? 0;
  const cur = all && shown > 0 ? all[shown - 1] : null;
  const next = all && shown < total ? all[shown] : null;
  const wallSince = (performance.now() - lastWall.current) / 1000;
  const gapRec = next && cur ? Math.max(0, (tsSeconds(next.ts) ?? 0) - (tsSeconds(cur.ts) ?? 0)) : 0;
  const delay = next ? replayDelay(cur?.ts, next.ts, speed) : 0;
  const along = playing && delay > 0 ? Math.min(wallSince / delay, 1) : 0;
  const elapsed = (cur ? (tsSeconds(cur.ts) ?? t0) - t0 : 0) + along * gapRec;
  const endS = all?.length ? (tsSeconds(all[total - 1].ts) ?? t0) - t0 : 0;
  return {
    shown, playing, speed, total, elapsed, endS, next, t0,
    nextIn: next ? Math.max(1, Math.ceil(delay - (playing ? wallSince : 0))) : 0,
    toggle: () => { if (shown >= total) { setShown(0); setPlaying(true); setKey((k) => k + 1); } else setPlaying((p) => !p); },
    setSpeed: (n: number) => { setSpeed(n); setKey((k) => k + 1); },
    restart: () => { setShown(0); setPlaying(true); setKey((k) => k + 1); },
    skipEnd: () => { setShown(total); setPlaying(false); },
    seek: (seq: number) => { setShown(seq); setKey((k) => k + 1); },
  };
}

/** Live: attach to the SSE stream (events so far arrive first). */
function useLive(caseId: string, run: string | undefined, enabled: boolean) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || !run) return;
    setEvents([]); setDone(false); setErr(null);
    return data.stream(caseId, run, {
      onEvent: (e) => setEvents((prev) => (prev.some((p) => p.seq === e.seq) ? prev : [...prev, e])),
      onDone: () => setDone(true),
      onError: (m) => setErr(m),
    });
  }, [caseId, run, enabled]);
  return { events, done, err };
}

function Act({ a, t0 }: { a: TraceEvent; t0: number }) {
  const [open, setOpen] = useState(false);
  const d = a.detail || {};
  const honest = a.type === "retry" || a.type === "fallback" || a.type === "error";
  const title = a.type === "retry" ? `retried: ${d.kind} (${d.step}, attempt ${d.attempt})`
    : a.type === "fallback" ? "fallback: deep model kept timing out, one try on the fast model"
    : a.type === "sql_query" ? (d.ok ? `Ran SQL on the evidence snapshot · ${d.rows} rows` : `SQL refused: ${d.error}`)
    : a.title;
  const meta = [modelName(a.model), a.receipt_id, a.type === "investigator_started" ? `${(d.questions || []).length} question(s)` : null]
    .filter(Boolean).join(" · ");
  return (
    <div style={sx(`font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.45;color:${honest ? "#8b1e17" : "#1a1814"};animation:${inAnim}`)}>
      <div style={sx("display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap")}><span><span style={sx("color:#5e574b")}>{clock((tsSeconds(a.ts) ?? t0) - t0)}</span> {title}</span>
        {a.type === "sql_query" && d.sql && <button onClick={() => setOpen((o) => !o)} style={sx("background:none;border:0;padding:0;color:#3d5a86;text-decoration:underline;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer")}>{open ? "hide SQL" : "show SQL"}</button>}
      </div>
      {meta && <div style={sx("color:#5e574b;font-size:10px")}>{meta}</div>}
      {honest && a.type !== "fallback" && d.error && <div style={sx("color:#5e574b;font-size:10px;word-break:break-word")}>{String(d.error).slice(0, 160)}</div>}
      {open && <pre style={sx("margin:6px 0 2px;padding:10px;background:#1a1814;color:#e8e2d4;font-size:11px;white-space:pre-wrap;word-break:break-word")}>{d.sql}</pre>}
    </div>
  );
}

function ClaimSheet({ c, tab, i }: { c: ClaimCard; tab: string; i: number }) {
  const decided = c.status !== "UNVERIFIED";
  return (
    <div data-claim={c.id} style={sx(`position:relative;display:flex;flex-direction:column;gap:0;animation:${inAnim}`)}>
      <div style={sx(`background:#f6f1e6;border:1px solid #d6ccb7;border-top:3px solid ${tab};padding:12px 13px;box-shadow:0 1px 0 rgba(0,0,0,.06),0 6px 14px rgba(0,0,0,.16);rotate:${ROT[(c.seq + i) % 5]};display:flex;flex-direction:column;gap:8px`)}>
        <div style={sx("display:flex;justify-content:space-between;gap:8px;align-items:flex-start")}>
          <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;line-height:1.5;color:#5e574b;word-break:break-word")}>CLAIM {c.id} · {c.receipt ?? "no receipt"}<br />{modelName(c.model)}{c.verified ? ` · evidence ${c.verified} verified` : ""}</div>
          {!decided && <span style={sx("flex:0 0 auto;border:1.5px dashed #56606b;color:#56606b;padding:2px 6px;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.1em;rotate:3deg")}>UNVERIFIED</span>}
          {decided && <span data-stamp={c.status} style={sx(`flex:0 0 auto;border:2.5px solid ${stampColor(c.status)};color:${stampColor(c.status)};padding:3px 7px;font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:12px;letter-spacing:.1em;rotate:${c.status === "ACCEPTED" ? "-6deg" : "5deg"};animation:${stampAnim};mix-blend-mode:multiply`)}>{c.status}</span>}
        </div>
        <p style={sx(`margin:0;font-size:18px;line-height:1.3;text-decoration:${c.dropped && !c.rev ? "line-through" : "none"};color:${c.dropped && !c.rev ? "#7d766a" : "#1a1814"};text-wrap:pretty`)}>{c.text}</p>
        {c.note && <p style={sx(`margin:0;font-size:16px;font-style:italic;line-height:1.3;color:${stampColor(c.status)};animation:${stampAnim}`)}>Skeptic: {c.note}</p>}
        {c.reworkRequested && !c.rev && !c.dropped && <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8b1e17;letter-spacing:.04em")}>SENT BACK ONCE · {c.reworkRequested}</div>}
        {c.dropped && !c.rev && <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8b1e17;letter-spacing:.08em")}>DROPPED · KEPT ON FILE · {c.dropped.toUpperCase()}</div>}
      </div>
      {c.rev && (
        <div style={sx(`position:relative;margin:-14px 0 0 14px;background:#fbf8f1;border:1px solid #d6ccb7;padding:16px 13px 12px;box-shadow:0 8px 18px rgba(0,0,0,.22);rotate:1.4deg;display:flex;flex-direction:column;gap:8px;animation:${inAnim}`)}>
          <span style={sx("position:absolute;top:-10px;left:22px;width:12px;height:30px;border:2px solid #8a8f96;border-radius:6px")}></span>
          <div style={sx("display:flex;justify-content:space-between;gap:8px;align-items:flex-start")}>
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;line-height:1.5;color:#5e574b;word-break:break-word")}>REVISED {c.id}′ · {c.rev.receipt ?? "no receipt"}<br />{modelName(c.rev.model)}</div>
            {c.rev.status === "UNVERIFIED" && <span style={sx("flex:0 0 auto;border:1.5px dashed #56606b;color:#56606b;padding:2px 6px;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.1em;rotate:3deg")}>UNVERIFIED</span>}
            {c.rev.status !== "UNVERIFIED" && <span data-stamp={c.rev.status} style={sx(`flex:0 0 auto;border:2.5px solid ${stampColor(c.rev.status)};color:${stampColor(c.rev.status)};padding:3px 7px;font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:12px;letter-spacing:.1em;rotate:-6deg;animation:${stampAnim};mix-blend-mode:multiply`)}>{c.rev.status}</span>}
          </div>
          <p style={sx(`margin:0;font-size:18px;line-height:1.3;text-wrap:pretty;text-decoration:${c.dropped ? "line-through" : "none"}`)}>{c.rev.text}</p>
          {c.rev.note && <p style={sx(`margin:0;font-size:16px;font-style:italic;line-height:1.3;color:${stampColor(c.rev.status)}`)}>Skeptic: {c.rev.note}</p>}
          {c.dropped && <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8b1e17;letter-spacing:.08em")}>DROPPED · KEPT ON FILE · {c.dropped.toUpperCase()}</div>}
        </div>
      )}
    </div>
  );
}

function Notes({ items, t0 }: { items: TraceEvent[]; t0: number }) {
  if (!items.length) return null;
  return <div style={sx("display:flex;flex-direction:column;gap:4px;max-width:820px")}>{items.map((a) => <Act key={a.seq} a={a} t0={t0} />)}</div>;
}

function Sections({ b, t0, nowS, caseId }: { b: Board; t0: number; nowS: number; caseId: string }) {
  const nav = useNavigate();
  const pending = pendingReviews(b);
  const mem = b.memory?.detail || {};
  const obs = mem.observed_this_case || {};
  const custodians: string[] = mem.custodian_wallets || [];
  const lastSk = b.skepticLog[b.skepticLog.length - 1];
  const skWorking = b.claims.length > 0 && !b.verdict && (pending > 0 || b.claims.some((c) => c.reworkRequested && !c.rev && !c.dropped));
  const vd = b.verdict?.detail || {};
  const box = (s: string) => sx(`flex:1 1 300px;border:1px dashed #3a3732;padding:18px;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#9a9384;${s}`);
  return (
    <div style={sx("flex:3 1 640px;min-width:0;display:flex;flex-direction:column;gap:44px")}>
      <section style={sx("display:flex;flex-direction:column;gap:16px")}>
        <div style={sx("display:flex;gap:14px;align-items:baseline")}><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>A</span><h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:34px;color:#f1ece1")}>Case opened</h2></div>
        <div style={sx("display:flex;gap:20px;flex-wrap:wrap")}>
          {b.opened ? (
            <div style={sx(`flex:1 1 300px;min-width:0;background:#efe9dc;color:#1a1814;padding:18px 20px;font-family:'IBM Plex Mono',monospace;font-size:12px;line-height:1.7;animation:${inAnim};rotate:-.6deg;box-shadow:0 8px 20px rgba(0,0,0,.35)`)}>
              <div style={sx("font-size:10px;letter-spacing:.14em;color:#5e574b;margin-bottom:6px")}>ARCHIVE RECORD · SEQ {b.opened.seq} · RUN {b.opened.run_id}</div>
              <div>{b.opened.title}</div>
              <div style={sx("color:#5e574b;word-break:break-word")}>Evidence snapshot frozen in Zetaris: {Object.values(b.opened.detail.snapshot_tables || {}).map((t) => String(t).split(".").pop()!.replace(/^m_[0-9a-f]+_/, "")).join(", ")}</div>
            </div>
          ) : <div style={box("")}>Snapshotting the token's public data…</div>}
          {b.memory && (
            <div style={sx(`flex:1 1 300px;min-width:0;background:#f6f2e8;background-image:repeating-linear-gradient(#f6f2e8 0 25px,#c9d3e0 25px 26px);color:#1a1814;padding:14px 20px 18px;border-top:2px solid #b0463a;animation:${inAnim};rotate:.9deg;box-shadow:0 8px 20px rgba(0,0,0,.35)`)}>
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#5e574b;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap")}><span>H-MEM · MEMORY RECALLED</span><span>SEQ {b.memory.seq} · NO MODEL (RULE-BASED)</span></div>
              <div style={sx("font-size:19px;margin-top:6px")}>{b.memory.title}</div>
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#5e574b;margin-top:2px")}>
                {obs.created != null ? `${obs.created?.length ?? obs.created} new, ${obs.updated?.length ?? obs.updated} updated facts for this case` : "facts for this case recorded"}
                {mem.seconds != null ? ` · recall ${mem.seconds} s` : ""}
                {custodians.length ? ` · likely custodian: ${custodians.map((w) => `${w.slice(0, 4)}…${w.slice(-4)}`).join(", ")}` : ""}
              </div>
            </div>
          )}
        </div>
      </section>

      <section style={sx("display:flex;flex-direction:column;gap:16px")}>
        <div style={sx("display:flex;gap:14px;align-items:baseline")}><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>B</span><h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:34px;color:#f1ece1")}>The plan</h2></div>
        {b.plan ? (
          <div style={sx(`position:relative;background:#efe9dc;background-image:radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px);background-size:3px 3px;color:#1a1814;padding:24px 28px 24px 52px;animation:${inAnim};box-shadow:0 10px 24px rgba(0,0,0,.35);max-width:820px`)}>
            <div style={sx("position:absolute;left:18px;top:28px;bottom:28px;display:flex;flex-direction:column;justify-content:space-between")}><span style={sx("width:10px;height:10px;border-radius:50%;background:#131210")}></span><span style={sx("width:10px;height:10px;border-radius:50%;background:#131210")}></span></div>
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.12em;color:#5e574b;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap")}><span>PLANNER · {modelShort(b.plan.model).toUpperCase()}</span><span>{b.plan.receipt_id}</span></div>
            <ol style={sx("margin:14px 0 0;padding-left:22px;display:flex;flex-direction:column;gap:8px;font-size:19px;line-height:1.35")}>
              {(b.plan.detail.questions || []).map((q: any) => (
                <li key={q.id ?? q.question} style={sx("text-wrap:pretty")}>{q.question} <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b;letter-spacing:.06em")}>→ {String(q.investigator).toUpperCase()}</span></li>
              ))}
            </ol>
          </div>
        ) : <div style={box("flex:none")}>The planner is reading the snapshot and setting 3 to 5 questions.</div>}
        <Notes items={b.acts["planner"] || []} t0={t0} />
      </section>

      <section style={sx("display:flex;flex-direction:column;gap:16px")}>
        <div style={sx("display:flex;gap:14px;align-items:baseline;flex-wrap:wrap")}><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>C</span><h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:34px;color:#f1ece1")}>Investigation</h2><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>3 AGENTS IN PARALLEL · {b.claims.length} CLAIMS FILED</span></div>
        <div style={sx("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:18px;align-items:start")}>
          {LANE_DEFS.map((L) => {
            const st = laneState(b, L.key);
            const claims = b.claims.filter((c) => c.lane === L.key);
            const since = st.lastTs ? Math.max(0, Math.floor(nowS - ((tsSeconds(st.lastTs) ?? t0) - t0))) : 0;
            return (
              <div key={L.key} data-lane={L.key} style={sx("display:flex;flex-direction:column;min-width:0")}>
                <div style={sx("display:flex")}><div style={sx(`background:${L.tab};color:#f3eee3;padding:8px 14px 6px;border-radius:6px 6px 0 0;font-size:17px`)}>{L.name}</div></div>
                <div style={sx(`background:#e4dccb;border-top:3px solid ${L.tab};padding:14px;display:flex;flex-direction:column;gap:14px;min-height:220px;color:#1a1814`)}>
                  <div style={sx("display:flex;gap:8px;align-items:flex-start;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.5")}>
                    <span style={sx(`flex:0 0 7px;height:7px;margin-top:4px;border-radius:50%;background:${st.working ? "#b8862f" : st.started ? GREEN : "#9a9384"};animation:${st.working ? pulse : "none"}`)}></span>
                    <span style={sx("flex:1")}><span style={sx("color:#1a1814")}>{st.now}</span><br /><span style={sx("color:#5e574b")}>{st.working ? `for ${since} s · ${modelShort(st.model) || "—"}` : st.started ? `${claims.length} claims filed` : "—"}</span></span>
                  </div>
                  <div style={sx("display:flex;flex-direction:column;gap:6px;border-top:1px solid #cbbfa8;padding-top:10px")}>
                    {(b.acts[L.key] || []).map((a) => <Act key={a.seq} a={a} t0={t0} />)}
                  </div>
                  {claims.map((c, i) => <ClaimSheet key={c.id} c={c} tab={L.tab} i={i} />)}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section style={sx("display:flex;flex-direction:column;gap:16px")}>
        <div style={sx("display:flex;gap:14px;align-items:baseline;flex-wrap:wrap")}><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>D</span><h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:34px;color:#f1ece1")}>Skeptic review</h2><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>{b.decisions} DECISIONS · {pending} AWAITING REVIEW</span></div>
        <div style={sx("display:flex")}><div style={sx("background:#2a2824;color:#f3eee3;padding:8px 14px 6px;border-radius:6px 6px 0 0;font-size:17px")}>Skeptic</div></div>
        <div style={sx("margin-top:-16px;background:#e4dccb;border-top:3px solid #2a2824;padding:16px;color:#1a1814;display:flex;flex-direction:column;gap:10px")}>
          <div style={sx("display:flex;gap:8px;align-items:flex-start;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.5")}>
            <span style={sx(`flex:0 0 7px;height:7px;margin-top:4px;border-radius:50%;background:${skWorking ? "#b8862f" : b.claims.length ? GREEN : "#9a9384"};animation:${skWorking ? pulse : "none"}`)}></span>
            <span><span>{!b.claims.length ? "Waiting for the first claim" : skWorking ? `Reviewing ${pending} claim${pending === 1 ? "" : "s"}…` : "Finished · every claim reviewed"}</span><br />
              <span style={sx("color:#5e574b")}>{skWorking && lastSk ? `for ${Math.max(0, Math.floor(nowS - ((tsSeconds(lastSk.ts) ?? t0) - t0)))} s · ${modelShort(lastSk.model) || "Nemotron 3.5 Super"}` : ""}</span></span>
          </div>
          <div style={sx("display:flex;flex-direction:column;gap:4px;border-top:1px solid #cbbfa8;padding-top:10px")}>
            {b.skepticLog.map((e) => {
              const d = e.detail || {};
              const color = e.type === "skeptic_decision" ? (d.decision === "accept" ? GREEN : RED) : e.type === "retry" || e.type === "fallback" ? "#5e574b" : "#1a1814";
              const title = e.type === "skeptic_decision" ? `${d.decision === "accept" ? "ACCEPTED" : "REJECTED"} ${d.id}${d.round === "re_review" ? "′" : ""}`
                : e.type === "rework_requested" ? `REWORK ${d.id} → sent back once`
                : e.type === "claim_dropped" ? `Dropped ${d.id} · kept on file`
                : e.type === "retry" ? `retried: ${d.kind} (attempt ${d.attempt})` : e.type === "fallback" ? "fallback: one try on the fast model" : e.title;
              return (
                <div key={e.seq} style={sx(`display:flex;gap:10px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.5;animation:${inAnim}`)}>
                  <span style={sx("color:#5e574b")}>{clock((tsSeconds(e.ts) ?? t0) - t0)}</span><span style={sx(`color:${color};font-weight:600`)}>{title}</span><span style={sx("color:#5e574b")}>{[modelShort(e.model), e.receipt_id].filter(Boolean).join(" · ")}</span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section style={sx("display:flex;flex-direction:column;gap:16px")}>
        <div style={sx("display:flex;gap:14px;align-items:baseline")}><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>E</span><h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:34px;color:#f1ece1")}>Verdict</h2></div>
        <Notes items={b.acts["verdict"] || []} t0={t0} />
        {b.verdict ? (
          <div data-testid="board-verdict" style={sx(`position:relative;background:#efe9dc;background-image:radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px);background-size:3px 3px;color:#1a1814;padding:clamp(22px,3vw,40px);box-shadow:0 18px 40px rgba(0,0,0,.45);animation:${sheetAnim};display:flex;flex-direction:column;gap:18px`)}>
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.12em;color:#5e574b;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap")}><span>COVER SHEET · CASE {caseId}</span><span>{[modelShort(b.verdict.model).toUpperCase(), b.verdict.receipt_id].filter(Boolean).join(" · ") || `SEQ ${b.verdict.seq}`}</span></div>
            <div style={sx(`align-self:flex-start;border:4px solid ${labelColor(vd.label)};color:${labelColor(vd.label)};padding:8px 22px;font-size:clamp(44px,6vw,80px);line-height:1;letter-spacing:.04em;rotate:-3deg;mix-blend-mode:multiply;animation:${stampAnim}`)}>{labelText(vd.label)}</div>
            <p style={sx("margin:0;font-size:clamp(22px,2.2vw,30px);line-height:1.25;max-width:760px;text-wrap:pretty")}>{vd.one_line}</p>
            <div style={sx("display:flex;gap:10px;flex-wrap:wrap")}>
              <button onClick={() => nav(`/case/${caseId}/verdict`)} style={sx("padding:12px 20px;background:#1a1814;color:#efe9dc;border:0;font-family:'IBM Plex Mono',monospace;font-size:12px;cursor:pointer")}>Open the verdict and its evidence</button>
            </div>
          </div>
        ) : b.errors.length && !b.events.some((e) => e.type === "verdict") && b.errors.some((e) => e.detail?.step === "run_failed") ? (
          <div style={sx("border:1px dashed #8b1e17;padding:28px;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#e58a7f;line-height:1.6")}>The run stopped before a verdict: {b.errors[b.errors.length - 1].detail?.error}</div>
        ) : (
          <div style={sx("border:1px dashed #3a3732;padding:28px;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#9a9384;line-height:1.6")}>The cover sheet is filed once the Skeptic has reviewed every claim.<br />{pending} claims awaiting review · step {b.events.length}</div>
        )}
      </section>
    </div>
  );
}

export default function BoardPage() {
  const { caseId = "" } = useParams();
  const [q] = useSearchParams();
  const { setTopRight, setLastCase, reloadCases, health } = useApp();
  const runParam = q.get("run") || undefined;
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [trace, setTrace] = useState<TraceEvent[] | null>(null);
  const [runId, setRunId] = useState<string | undefined>(runParam);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const wantLive = q.get("live") === "1";
  const live = wantLive || detail?.meta.status === "running";

  useEffect(() => { setLastCase(caseId); }, [caseId]);
  // Case detail (pocket, mint, symbol). For a live run it may not exist yet: retry.
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const load = () => data.caseDetail(caseId, runParam).then((d) => { if (!stop) setDetail(d); })
      .catch((e) => { if (!stop && wantLive) timer = setTimeout(load, 3000); else if (!stop) setErr(String(e.message || e)); });
    load();
    return () => { stop = true; clearTimeout(timer); };
  }, [caseId, runParam, wantLive]);
  // Recorded trace for replay.
  useEffect(() => {
    if (wantLive) return;
    data.trace(caseId, runParam).then((t) => { setTrace(t.events); setRunId(t.run_id); }).catch((e) => setErr(String(e.message || e)));
  }, [caseId, runParam, wantLive]);

  const player = useReplay(caseId, runId, trace, !live && !!trace);
  const liveS = useLive(caseId, runParam ?? detail?.meta.run_id, live);
  useEffect(() => { if (liveS.done) { data.caseDetail(caseId, runParam).then(setDetail).catch(() => {}); reloadCases(); } }, [liveS.done]);
  const liveCount = liveS.events.length;
  useEffect(() => {   // refresh the pocket once the case file exists on a live run
    if (live && !detail?.summary && liveCount >= 2) data.caseDetail(caseId, runParam).then(setDetail).catch(() => {});
  }, [live, liveCount]);

  const events = live ? liveS.events : (trace || []).slice(0, player.shown);
  const all = live ? liveS.events : trace || [];
  const board = useMemo(() => reduceBoard(events), [events]);
  const total = live ? events.length : player.total;
  const shownN = live ? events.length : player.shown;
  const rid = runId || detail?.meta.run_id || events[0]?.run_id || "";
  useEffect(() => { setTopRight(`RUN ${rid || "—"} · SEQ ${shownN}/${total}`); return () => setTopRight(null); }, [rid, shownN, total]);

  if (err) return <Loading what={`Could not open case ${caseId}: ${err}`} />;
  if (!detail && !live) return <Loading what={`Opening case ${caseId}…`} />;

  const t0 = tsSeconds(all[0]?.ts) ?? Date.now() / 1000;
  const liveNow = Date.now() / 1000 - t0;
  const nowS = live ? (liveS.done ? (tsSeconds(all[all.length - 1]?.ts) ?? t0) - t0 : liveNow) : player.elapsed;
  const endS = live ? nowS : player.endS;
  const mint = detail?.meta.mint || board.opened?.detail?.mint || "";
  const symbol = detail?.meta.symbol || board.opened?.detail?.symbol || caseId;
  const openedTs = all[0]?.ts || detail?.meta.recorded_at || null;
  const closed = live ? liveS.done : player.shown >= player.total && player.total > 0;
  const nowLine = closed
    ? `Case closed · ${total} events · ${board.verdict ? "verdict filed" : "no verdict"}`
    : live
      ? `Live · ${events.length} events so far${events.length ? ` · last: ${events[events.length - 1].type.replace(/_/g, " ")}` : " · waiting for the first event"}${liveS.err ? ` · ${liveS.err}` : ""}`
      : player.next
        ? `${player.playing ? "Now" : "Paused"} · next: ${player.next.type.replace(/_/g, " ")}${player.next.agent && !["casefile", "h-mem"].includes(player.next.agent) ? ` (${player.next.agent})` : ""} in ${player.nextIn} s at ${player.speed}x`
        : "";
  const pill = live ? "LIVE" : health?.mode === "static" ? "HOSTED REPLAY" : "REPLAY";
  const pillColor = live ? "#7fbf8c" : "#d9a24a";
  const ctl = (on: boolean) => sx(`padding:7px 10px;background:${on ? "#e8e2d4" : "transparent"};color:${on ? "#131210" : "#e8e2d4"};border:1px solid #4a463f;font-size:12px;cursor:pointer`);

  return (
    <main data-screen-label="02 Case board" style={sx("max-width:1440px;margin:0 auto;padding:28px clamp(16px,3vw,48px) 80px")}>
      <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;margin-bottom:18px;overflow-wrap:anywhere")}>Case shelf / {live ? "Live case" : "Recorded cases"} / {caseId}</div>
      <div style={sx("display:flex;gap:28px;flex-wrap:wrap;justify-content:space-between;align-items:flex-end")}>
        <div style={sx("flex:1 1 520px;min-width:0")}>
          <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.1em;color:#cfc8b8;overflow-wrap:anywhere")}>CASE {caseId} · OPENED {date(openedTs).toUpperCase()} · {timeUtc(openedTs)}</div>
          <h1 style={sx("margin:10px 0 12px;font-weight:400;font-size:clamp(56px,7vw,110px);line-height:1;color:#f1ece1;overflow-wrap:anywhere")}>{symbol}</h1>
          <div style={sx("display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#bdb6a6")}>
            <span title="A token's mint is its unique on-chain address." style={sx("border-bottom:1px dotted #9a9384;cursor:help")}>Mint</span>
            <span style={sx("color:#e8e2d4")} title={mint}>{mint ? `${mint.slice(0, 4)}…${mint.slice(-4)}` : "—"}</span>
            <button onClick={() => { copyText(mint); setCopied(true); setTimeout(() => setCopied(false), 1400); }} style={sx("background:none;border:1px solid #4a463f;color:#e8e2d4;padding:3px 8px;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer")}>{copied ? "Copied" : "Copy"}</button>
            <span data-testid="mode-pill" style={sx(`padding:3px 9px;border:1px solid ${pillColor};color:${pillColor};letter-spacing:.12em;font-size:11px`)}>{pill}</span>
          </div>
        </div>
        <div style={sx("flex:0 1 420px;display:flex;flex-direction:column;gap:12px;font-family:'IBM Plex Mono',monospace")}>
          <div style={sx("display:flex;justify-content:space-between;align-items:baseline;gap:12px")}>
            <span style={sx("font-size:30px;color:#f1ece1")}>{clock(nowS)}<span style={sx("font-size:13px;color:#9a9384")}> / {live && !liveS.done ? "live" : clock(endS)}</span></span>
            <span data-testid="step-counter" style={sx("font-size:11px;color:#9a9384;letter-spacing:.1em")}>STEP {shownN} OF {total}</span>
          </div>
          {!live && (
            <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}>
              <button data-testid="play" onClick={player.toggle} style={sx("padding:7px 12px;background:#e8e2d4;color:#131210;border:0;font-size:12px;cursor:pointer;min-width:72px")}>{player.playing ? "Pause" : closed ? "Replay" : "Play"}</button>
              {[1, 4, 16].map((n) => <button key={n} data-testid={`speed-${n}`} onClick={() => player.setSpeed(n)} style={ctl(player.speed === n)}>{n}x</button>)}
              <button onClick={player.restart} style={ctl(false)}>Restart</button>
              <button data-testid="skip-end" onClick={player.skipEnd} style={ctl(false)}>Skip to end</button>
            </div>
          )}
        </div>
      </div>

      <div style={sx("position:relative;height:22px;margin:24px 0 6px")}>
        <div style={sx("position:absolute;left:0;right:0;top:10px;height:1px;background:#3a3732")}></div>
        <div style={sx(`position:absolute;left:0;top:10px;height:1px;background:#e8e2d4;width:${endS > 0 ? Math.min(100, (nowS / endS) * 100) : closed ? 100 : 0}%`)}></div>
        {all.map((e) => {
          const at = (tsSeconds(e.ts) ?? t0) - t0;
          const left = endS > 0 ? Math.min(100, (at / endS) * 100) : 0;
          return (
            <button key={e.seq} title={`${e.seq} · ${e.type} · ${clock(at)}`} onClick={() => !live && player.seek(e.seq)}
              style={sx(`position:absolute;left:${left}%;top:3px;width:9px;height:15px;margin-left:-4px;padding:0;border:0;cursor:${live ? "default" : "pointer"};background:none;display:flex;justify-content:center`)}>
              <span style={sx(`width:1px;height:15px;background:${e.seq <= shownN ? "#e8e2d4" : "#5a554c"}`)}></span>
            </button>
          );
        })}
      </div>
      <div style={sx("display:flex;gap:10px;align-items:center;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#cfc8b8;margin-bottom:36px;flex-wrap:wrap")}>
        <span style={sx(`width:7px;height:7px;border-radius:50%;background:#d9a24a;animation:${(live ? !liveS.done : player.playing) ? pulse : "none"}`)}></span>
        <span data-testid="now-line">{nowLine}</span>
      </div>

      <div style={sx("display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start")}>
        <Sections b={board} t0={t0} nowS={nowS} caseId={caseId} />
        <EvidencePocket detail={detail} board={board} />
      </div>
    </main>
  );
}

