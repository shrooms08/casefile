import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BusyError, data } from "../data";
import { isLive, useApp } from "../App";
import { sx } from "../lib/sx";
import { BLUE, OCH_TAB, RED, RED_TAB, ROT, date, disagrees, duration, labelColor, labelTab, labelText, shortAddr, today } from "../lib/format";
import { RugcheckStrip } from "./common";

const STEPS: [string, string, string][] = [
  ["Open case", "Snapshot the token’s public data into a frozen evidence file.", BLUE],
  ["Plan", "A planner sets 3 to 5 questions to answer.", "#3e382f"],
  ["Investigate", "Three agents query the evidence in parallel and file claims.", OCH_TAB],
  ["Skeptic review", "Every claim is accepted, sent back for rework, or dropped.", RED_TAB],
  ["Verdict", "A stamped cover sheet where every line cites a receipt.", RED],
];

function NewCase() {
  const { health } = useApp();
  const nav = useNavigate();
  const live = isLive(health);
  const [addr, setAddr] = useState("");
  const [busy, setBusy] = useState<{ case_id: string; run_id: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const open = async () => {
    if (!live || !addr.trim() || sending) return;
    setErr(null); setBusy(null); setSending(true);
    try {
      const r = await data.investigate(addr.trim());
      nav(`/case/${r.case_id}?run=${r.run_id}&live=1`);
    } catch (e) {
      if (e instanceof BusyError) setBusy(e.running);
      else setErr(String((e as Error).message || e));
    } finally {
      setSending(false);
    }
  };
  return (
    <div style={sx("max-width:880px;background:#efe9dc;background-image:radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px);background-size:3px 3px;color:#1a1814;padding:22px;display:flex;flex-direction:column;gap:12px;box-shadow:0 18px 40px rgba(0,0,0,.4)")}>
      <label htmlFor="mint" style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#5e574b")}>NEW CASE · <span title="A token's mint is its unique on-chain address." style={sx("border-bottom:1px dotted #5e574b;cursor:help")}>TOKEN MINT ADDRESS</span></label>
      <form onSubmit={(e) => { e.preventDefault(); open(); }} style={sx("display:flex;gap:10px;flex-wrap:wrap")}>
        <input id="mint" disabled={!live} value={addr} onChange={(e) => setAddr(e.target.value)} placeholder="Paste a Solana token address"
          style={sx(`flex:1 1 320px;min-width:0;font-family:'IBM Plex Mono',monospace;font-size:15px;padding:14px 16px;border:1px solid #1a1814;background:${live ? "#fbf8f1" : "#e2dbcc"};color:#1a1814;outline:none`)} />
        <button type="submit" disabled={!live || sending}
          style={sx(`flex:0 0 auto;padding:14px 26px;background:#1a1814;color:#efe9dc;border:0;font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.06em;cursor:${live ? "pointer" : "not-allowed"};opacity:${live ? "1" : ".45"}`)}>
          {sending ? "Opening…" : "Open case"}</button>
      </form>
      {!live && <div style={sx("font-size:16px;font-style:italic;color:#5e574b")}>Live investigations need the local stack. Watch a recorded case below.</div>}
      {busy && <div role="alert" style={sx("font-size:16px;font-style:italic;color:#8b1e17")}>Another case is being investigated. <Link to={`/case/${busy.case_id}?run=${busy.run_id}&live=1`} style={sx("color:#8b1e17")}>Follow it on the case board</Link>.</div>}
      {err && <div role="alert" style={sx("font-size:16px;font-style:italic;color:#8b1e17")}>{err}</div>}
    </div>
  );
}

export default function Shelf() {
  const { cases, health } = useApp();
  const nav = useNavigate();
  const list = cases || [];
  const durations = list.map((c) => c.duration_s).filter((x): x is number => typeof x === "number");
  const avgMin = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length / 60) : null;
  const live = isLive(health);
  return (
    <main data-screen-label="01 Home" style={sx("max-width:1440px;margin:0 auto;padding:clamp(28px,5vw,64px) clamp(16px,3vw,48px) 80px")}>
      <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;margin-bottom:28px")}>Desk / New case</div>
      <div style={sx("display:flex;gap:40px;flex-wrap:wrap;align-items:flex-end;justify-content:space-between")}>
        <h1 style={sx("flex:1 1 640px;margin:0;font-weight:400;font-size:clamp(44px,6.4vw,96px);line-height:1;letter-spacing:-.02em;text-wrap:balance;color:#f1ece1")}>RugCheck says it's fine. <span style={sx("font-style:italic")}>Casefile shows why it isn't.</span></h1>
        <div style={sx("flex:0 1 240px;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.6;color:#9a9384")}>Filed by agents.<br />Argued by a Skeptic.<br />Every line cites a receipt.<br /><br />{today()}</div>
      </div>
      <p style={sx("max-width:720px;font-size:clamp(19px,1.8vw,24px);line-height:1.4;color:#cfc8b8;margin:28px 0 40px;text-wrap:pretty")}>Agents investigate a Solana token, argue over the evidence, and hand you a verdict you can check.</p>
      <NewCase />

      <div style={sx("display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin:88px 0 28px;border-bottom:1px solid #2c2a26;padding-bottom:14px")}>
        <h2 style={sx("margin:0;font-weight:400;font-size:clamp(32px,3.4vw,48px);color:#f1ece1")}>Recorded cases</h2>
        <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;letter-spacing:.1em")}>{cases == null ? "LOADING" : `${list.length} FOLDERS · ${live ? "LIVE DESK" : "REPLAY"}`}</span>
      </div>
      <div style={sx("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:36px 28px")}>
        {list.map((c, i) => {
          const tab = labelTab(c.label), color = labelColor(c.label);
          const kind = c.status === "running" ? "LIVE" : c.source === "demo" ? "REPLAY" : "RECORDED";
          return (
            <button key={c.case_id} data-case={c.case_id} className="cf-folder" onClick={() => nav(`/case/${c.case_id}`)}
              style={sx("text-align:left;background:none;border:0;padding:0;cursor:pointer;display:flex;flex-direction:column;transition:translate 200ms ease")}>
              <div style={sx("display:flex")}><div style={sx(`background:${tab};color:#f3eee3;padding:8px 16px 6px;border-radius:6px 6px 0 0;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.1em`)}>FILE Nº {String(i + 1).padStart(2, "0")} · {kind}</div></div>
              <div style={sx(`background:${tab};padding:14px 14px 18px;border-radius:0 6px 6px 6px;width:100%`)}>
                <div style={sx(`background:#efe9dc;background-image:radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px);background-size:3px 3px;color:#1a1814;padding:18px;rotate:${ROT[i % 5]};box-shadow:0 6px 16px rgba(0,0,0,.3);display:flex;flex-direction:column;gap:10px;min-height:280px`)}>
                  <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap")}><span>CASE {c.case_id}</span><span title={c.mint}>{shortAddr(c.mint)}</span></div>
                  <div style={sx("display:flex;justify-content:space-between;align-items:center;gap:10px")}>
                    <span style={sx("font-size:44px;line-height:1;overflow-wrap:anywhere")}>{c.symbol}</span>
                    <span style={sx(`border:2.5px solid ${color};color:${color};padding:4px 9px;font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:13px;letter-spacing:.08em;rotate:-5deg;white-space:nowrap`)}>{labelText(c.label)}</span>
                  </div>
                  <p style={sx("margin:0;font-size:17px;line-height:1.35;text-wrap:pretty;flex:1")}>{c.one_line ?? (c.status === "running" ? "Investigation in progress." : "No verdict on file.")}</p>
                  <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b")}>{duration(c.duration_s).toUpperCase()} · {c.llm_calls ?? "—"} AGENT CALLS · {date(c.recorded_at).toUpperCase()}</div>
                  {disagrees(c.rugcheck_rugged, c.label) && <RugcheckStrip rugged={c.rugcheck_rugged} label={c.label} />}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div style={sx("display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin:96px 0 24px;border-bottom:1px solid #2c2a26;padding-bottom:14px")}>
        <h2 style={sx("margin:0;font-weight:400;font-style:italic;font-size:clamp(28px,2.8vw,40px);color:#f1ece1")}>How it works</h2>
        {avgMin != null && <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;letter-spacing:.1em")}>ABOUT {avgMin} MINUTES PER CASE</span>}
      </div>
      <div style={sx("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:2px")}>
        {STEPS.map(([title, text, color], i) => (
          <div key={title} style={sx(`padding:18px 18px 22px;background:#1b1a17;border-top:3px solid ${color};display:flex;flex-direction:column;gap:8px`)}>
            <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9a9384;letter-spacing:.12em")}>STEP 0{i + 1}</span>
            <span style={sx("font-size:22px;color:#f1ece1")}>{title}</span>
            <span style={sx("font-size:16px;line-height:1.35;color:#bdb6a6")}>{text}</span>
          </div>
        ))}
      </div>
    </main>
  );
}
