import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { data } from "../data";
import type { CaseDetail, Evidence } from "../data";
import { useApp } from "../App";
import { sx } from "../lib/sx";
import { ROT, date, disagrees, duration, host, labelColor, labelText, modelShort, shortAddr, value } from "../lib/format";
import { Loading, RugcheckStrip } from "./common";

interface Slip { id: string; table: string; field: string; value: string; source: string; url: string | null }

/** Receipt slips from the evidence of the accepted claims the why-lines cite (deduplicated). */
function buildSlips(detail: CaseDetail) {
  const v = detail.verdict!;
  const claims = new Map(v.accepted_claims.map((c) => [c.id, c]));
  const slips: Slip[] = [];
  const keyOf = (e: Evidence) => `${e.table}|${e.field}|${JSON.stringify(e.value)}`;
  const index = new Map<string, string>();
  const why = v.verdict.why.map((w) => {
    const claim = claims.get(w.claim_id);
    const chips: string[] = [];
    for (const e of claim?.evidence || []) {
      const k = keyOf(e);
      if (!index.has(k)) {
        const id = `E${index.size + 1}`;
        index.set(k, id);
        const source = e.table === "computed" ? `computed from the snapshot: ${e.formula ?? e.field}`
          : e.table === "H-MEM" ? `H-MEM desk memory${e.source_case ? ` · case ${e.source_case}` : ""}`
          : host(e.source_api_url) || "—";
        slips.push({ id, table: e.table, field: e.field, value: value(e.value), source, url: e.source_api_url });
      }
      const id = index.get(k)!;
      if (!chips.includes(id)) chips.push(id);
    }
    return { ...w, chips };
  });
  return { why, slips };
}

export default function VerdictPage() {
  const { caseId = "" } = useParams();
  const nav = useNavigate();
  const { cases, setLastCase } = useApp();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<{ w: number; e: string } | null>(null);
  const [pinned, setPinned] = useState<{ w: number; e: string } | null>(null);
  const [line, setLine] = useState<{ d: string; x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [shared, setShared] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => { setLastCase(caseId); setDetail(null); setErr(null); data.caseDetail(caseId).then(setDetail).catch((e) => setErr(String(e.message || e))); }, [caseId]);
  const built = useMemo(() => (detail?.verdict ? buildSlips(detail) : null), [detail]);
  const hl = hover || pinned;

  // The design's red thread from a hovered chip to its pinned slip.
  const measure = useCallback(() => {
    const r = root.current;
    if (!r || !hl) { setLine(null); return; }
    const a = r.querySelector(`[data-chip="${hl.w}-${hl.e}"]`), b = r.querySelector(`[data-slip="${hl.e}"]`);
    if (!a || !b) return;
    const R = r.getBoundingClientRect(), A = a.getBoundingClientRect(), B = b.getBoundingClientRect();
    const x1 = A.right - R.left, y1 = A.top + A.height / 2 - R.top, x2 = B.left - R.left + 16, y2 = B.top - R.top + 16;
    const mx = (x1 + x2) / 2, my = Math.max(y1, y2) + 50;
    setLine({ d: `M${x1} ${y1} Q${mx} ${my} ${x2} ${y2}`, x1, y1, x2, y2 });
  }, [hl?.w, hl?.e]);
  useLayoutEffect(() => { measure(); const t = setTimeout(measure, 220); return () => clearTimeout(t); }, [measure]);
  useEffect(() => { window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); }, [measure]);

  if (err) return <Loading what={`Could not open the verdict for ${caseId}: ${err}`} />;
  if (!detail) return <Loading what={`Opening the verdict for ${caseId}…`} />;
  const m = detail.meta;
  if (!detail.verdict || !built) return <Loading what={`Case ${caseId} has no verdict on file yet.`} />;
  const v = detail.verdict.verdict;
  const color = labelColor(v.label);
  const fileNo = String(Math.max(1, (cases || []).findIndex((c) => c.case_id === caseId) + 1)).padStart(2, "0");
  const unreviewed = (detail.verdict.dropped || []).filter((d) => /never reviewed/i.test(d.why)).length;
  const reviewed = unreviewed === 0 ? "Every claim was reviewed by the Skeptic agent." : `${unreviewed} claim(s) could not be reviewed and were left out.`;
  const others = (cases || []).filter((c) => c.case_id !== caseId);
  const anim = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "none" : "cfSheet 380ms ease-out both";
  const stampA = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "none" : "cfStamp 260ms cubic-bezier(.3,1.4,.5,1) both";

  return (
    <main data-screen-label="03 Verdict" style={sx("padding:28px 0 80px")}>
      <div style={sx("max-width:1440px;margin:0 auto;padding:0 clamp(16px,3vw,48px)")}>
        <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;margin-bottom:18px;overflow-wrap:anywhere")}>Case shelf / Verdicts / {caseId}</div>
        <div style={sx("display:flex;gap:28px;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;margin-bottom:36px")}>
          <div style={sx("flex:1 1 420px;min-width:0")}>
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.1em;color:#cfc8b8;overflow-wrap:anywhere")}>CASE {caseId} · <span title={m.mint}>{shortAddr(m.mint)}</span> · RUN {m.run_id}</div>
            <h1 style={sx("margin:8px 0 0;font-weight:400;font-size:clamp(56px,7vw,110px);line-height:1;color:#f1ece1;overflow-wrap:anywhere")}>{m.symbol}</h1>
          </div>
          <div style={sx("display:flex;gap:8px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:12px")}>
            <button onClick={() => nav(`/case/${caseId}`)} style={sx("padding:9px 14px;background:#e8e2d4;color:#131210;border:0;cursor:pointer")}>Watch the investigation</button>
            <button onClick={() => { navigator.clipboard?.writeText(`${location.origin}/case/${caseId}/verdict`).catch(() => {}); setShared(true); setTimeout(() => setShared(false), 1400); }} style={sx("padding:9px 14px;background:none;color:#e8e2d4;border:1px solid #4a463f;cursor:pointer")}>{shared ? "Link copied" : "Copy share link"}</button>
          </div>
        </div>
      </div>
      <div style={sx("background:#2b4470;padding:clamp(20px,4vw,56px) 0")}>
        {disagrees(m.rugcheck_rugged, v.label) && (
          <div style={sx("max-width:1440px;margin:0 auto 18px;padding:0 clamp(12px,3vw,48px);display:flex")}><RugcheckStrip rugged={m.rugcheck_rugged} label={v.label} /></div>
        )}
        <div ref={root} style={sx("position:relative;max-width:1440px;margin:0 auto;padding:0 clamp(12px,3vw,48px);display:flex;gap:36px;flex-wrap:wrap;align-items:flex-start")}>
          <div style={sx("flex:2 1 560px;min-width:0;display:flex")}>
            <div data-testid="verdict-sheet" style={sx(`position:relative;flex:1;min-width:0;background:#efe9dc;background-image:radial-gradient(rgba(0,0,0,.03) 1px,transparent 1px);background-size:3px 3px;color:#1a1814;padding:clamp(22px,3.4vw,52px) clamp(20px,3.4vw,52px) 28px clamp(40px,5vw,76px);box-shadow:0 24px 50px rgba(0,0,0,.4);animation:${anim}`)}>
              <div style={sx("position:absolute;left:clamp(14px,2vw,26px);top:48px;bottom:48px;display:flex;flex-direction:column;justify-content:space-between")}><span style={sx("width:11px;height:11px;border-radius:50%;background:#2b4470")}></span><span style={sx("width:11px;height:11px;border-radius:50%;background:#2b4470")}></span><span style={sx("width:11px;height:11px;border-radius:50%;background:#2b4470")}></span></div>
              <div style={sx("display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start")}>
                <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;line-height:1.6;color:#5e574b;max-width:220px")}>Verdict cover sheet.<br />Filed {date(m.recorded_at)}.<br />Reviewed by the Skeptic.</div>
                <span style={sx("border:1px solid #2b4470;color:#2b4470;padding:4px 10px;font-family:'IBM Plex Mono',monospace;font-size:12px")}>File Nº {fileNo}</span>
              </div>
              <div data-testid="verdict-label" style={sx(`margin:28px 0 22px;display:inline-block;border:5px solid ${color};color:${color};padding:10px 26px 6px;font-size:clamp(52px,8vw,124px);line-height:1;letter-spacing:.03em;rotate:-3deg;mix-blend-mode:multiply;animation:${stampA};max-width:100%;overflow-wrap:anywhere`)}>{labelText(v.label)}</div>
              <p data-testid="one-line" style={sx("margin:0 0 36px;font-size:clamp(24px,2.6vw,36px);line-height:1.2;max-width:820px;text-wrap:pretty")}>{v.one_line}</p>
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#5e574b;border-bottom:1px solid #1a1814;padding-bottom:8px;margin-bottom:6px")}>WHY · HOVER A LINE, CLICK A CHIP TO PIN ITS RECEIPT</div>
              <ol data-testid="why-lines" style={sx("list-style:none;margin:0;padding:0;display:flex;flex-direction:column")}>
                {built.why.map((w, i) => (
                  <li key={i} data-why={i} onMouseEnter={() => w.chips[0] && setHover({ w: i, e: w.chips[0] })} onMouseLeave={() => setHover(null)}
                    style={sx(`display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #d3c9b5;background:${hl && hl.w === i ? "rgba(176,40,29,.06)" : "transparent"}`)}>
                    <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#5e574b;padding-top:6px;flex:0 0 22px")}>{String(i + 1).padStart(2, "0")}</span>
                    <span style={sx("flex:1;min-width:0;font-size:20px;line-height:1.35;text-wrap:pretty")}><span data-testid="why-text">{w.sentence}</span>
                      <span style={sx("display:inline-flex;flex-wrap:wrap;gap:5px;margin-left:6px;vertical-align:2px")}>
                        <span title={`claim ${w.claim_id}`} style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b;padding:2px 0")}>{w.claim_id}</span>
                        {w.chips.map((id) => {
                          const on = !!hl && hl.w === i && hl.e === id;
                          return <button key={id} data-chip={`${i}-${id}`} onClick={() => { setPinned({ w: i, e: id }); setHover(null); }} onMouseEnter={() => setHover({ w: i, e: id })}
                            style={sx(`font-family:'IBM Plex Mono',monospace;font-size:11px;padding:2px 6px;border:1px solid #8b1e17;background:${on ? "#8b1e17" : "transparent"};color:${on ? "#f6f1e6" : "#8b1e17"};cursor:pointer`)}>{id}</button>;
                        })}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
              <div style={sx("margin-top:28px;display:flex;gap:16px;flex-wrap:wrap;align-items:baseline")}>
                <span style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#5e574b;flex:0 0 auto")}>WHAT WOULD CHANGE MY MIND</span>
                <span data-testid="change-mind" style={sx("flex:1 1 300px;font-size:20px;font-style:italic;line-height:1.35")}>{v.what_would_change_my_mind}</span>
              </div>
              <div style={sx("margin-top:36px;padding-top:12px;border-top:1px solid #1a1814;display:flex;gap:8px 20px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:10px;line-height:1.6;color:#3e382f")}>
                <span>MODELS {(v.models_used || m.models_used || []).map(modelShort).join(" · ")}</span><span>{m.llm_calls ?? detail.verdict.llm_calls} AGENT CALLS</span><span>DURATION {duration(m.duration_s ?? detail.verdict.seconds)}</span><span>{reviewed}</span>
              </div>
            </div>
            <div style={sx("flex:0 0 auto;display:flex;flex-direction:column;padding-top:44px;gap:6px")}>
              <div style={sx("background:#9c3328;color:#f3eee3;writing-mode:vertical-rl;padding:18px 7px;border-radius:0 8px 8px 0;font-size:16px")}>Verdict</div>
              <div style={sx("background:#3d5a86;color:#f3eee3;writing-mode:vertical-rl;padding:18px 7px;border-radius:0 8px 8px 0;font-size:16px")}>Evidence</div>
            </div>
          </div>
          <div style={sx("flex:1 1 300px;min-width:0;display:flex;flex-direction:column;padding-top:20px")}>
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#dfe5ef;margin-bottom:14px")}>PINNED RECEIPTS · {built.slips.length} SLIPS</div>
            {built.slips.map((s, i) => {
              const on = !!hl && hl.e === s.id;
              const pin = !!pinned && pinned.e === s.id;
              return (
                <div key={s.id} data-slip={s.id} onClick={() => { const w = built.why.findIndex((x) => x.chips.includes(s.id)); setPinned({ w, e: s.id }); setHover(null); }}
                  style={sx(`position:relative;margin-top:-6px;background:#ecdfae;color:#1a1814;padding:14px 16px 12px 30px;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.55;rotate:${on ? "0deg" : ROT[i % 5]};scale:${on ? "1.03" : "1"};z-index:${on ? 5 : 1 + i};outline:${on ? "2px solid #b0281d" : "none"};box-shadow:0 8px 18px rgba(0,0,0,.3);transition:rotate 200ms,scale 200ms;cursor:pointer;word-break:break-word`)}>
                  <span style={sx("position:absolute;left:12px;top:12px;width:9px;height:9px;border-radius:50%;background:#8b1e17")}></span>
                  <div style={sx("display:flex;justify-content:space-between;gap:8px;font-weight:600;letter-spacing:.1em")}><span>RECEIPT {s.id}</span><span style={sx("color:#8b1e17")}>{pin ? "PINNED" : ""}</span></div>
                  <div style={sx("display:grid;grid-template-columns:64px minmax(0,1fr);gap:1px 8px;margin-top:6px")}>
                    <span style={sx("color:#5e574b")}>TABLE</span><span>{s.table}</span>
                    <span style={sx("color:#5e574b")}>FIELD</span><span>{s.field}</span>
                    <span style={sx("color:#5e574b")}>VALUE</span><span style={sx("font-weight:600")}>{s.value}</span>
                    <span style={sx("color:#5e574b")}>SOURCE</span>{s.url ? <a href={s.url} target="_blank" rel="noreferrer" style={sx("color:#2b4470")}>{s.source}</a> : <span>{s.source}</span>}
                  </div>
                </div>
              );
            })}
          </div>
          {line && (
            <svg style={sx("position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible")}>
              <path d={line.d} fill="none" stroke="#b0281d" strokeWidth="1.6"></path>
              <circle cx={line.x1} cy={line.y1} r="3" fill="#b0281d"></circle>
              <circle cx={line.x2} cy={line.y2} r="3" fill="#b0281d"></circle>
            </svg>
          )}
        </div>
      </div>
      <div style={sx("max-width:1440px;margin:28px auto 0;padding:0 clamp(16px,3vw,48px);display:flex;gap:8px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:12px")}>
        <span style={sx("color:#9a9384;margin-right:6px")}>OTHER VERDICTS</span>
        {others.map((o) => <button key={o.case_id} onClick={() => nav(`/case/${o.case_id}/verdict`)} style={sx("background:none;border:1px solid #4a463f;color:#e8e2d4;padding:5px 10px;cursor:pointer")}>{o.symbol} · {labelText(o.label)}</button>)}
      </div>
    </main>
  );
}
