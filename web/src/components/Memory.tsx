import { useEffect, useState } from "react";
import { data } from "../data";
import type { MemoryItem, MemorySummary } from "../data";
import { useApp } from "../App";
import { sx } from "../lib/sx";
import { ROT, shortAddr } from "../lib/format";
import { Addr, Loading } from "./common";

const TIP_CUSTODIAN = "An exchange or wallet provider holding tokens for many users.";

function role(m: MemoryItem): { role: string; tip: string } {
  if (m.likely_custodian) return { role: "likely custodian", tip: TIP_CUSTODIAN };
  const r = m.roles.join(", ") || "seen";
  const tip = m.roles.includes("creator") ? "The wallet that deployed a token."
    : m.roles.includes("insider") ? "Flagged as an insider in a case." : "A top-20 holder in a case.";
  return { role: r, tip };
}

export default function MemoryPage() {
  const { cases } = useApp();
  const [mem, setMem] = useState<MemorySummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => { data.memory().then(setMem).catch((e) => setErr(String(e.message || e))); }, []);
  if (err) return <Loading what={`Could not read desk memory: ${err}`} />;
  if (!mem) return <Loading what="Reading desk memory…" />;
  const symbolOf = (cid: string) => cases?.find((c) => c.case_id === cid)?.symbol;
  const featured = mem.items.filter((m) => m.case_count >= 2 || m.likely_custodian);
  const shown = all ? mem.items : featured;
  return (
    <main data-screen-label="04 Memory" style={sx("max-width:1440px;margin:0 auto;padding:28px clamp(16px,3vw,48px) 80px")}>
      <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;margin-bottom:18px")}>Desk / Memory index</div>
      <div style={sx("display:flex;gap:40px;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;margin-bottom:44px")}>
        <h1 style={sx("margin:0;font-weight:400;font-size:clamp(48px,6vw,92px);line-height:1;color:#f1ece1")}>Desk memory <span style={sx("font-style:italic")}>(H-MEM)</span></h1>
        <p style={sx("flex:0 1 320px;margin:0;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.6;color:#9a9384")}>Wallets the desk has seen before. Agents check every new case against this index, so a known custodian isn't mistaken for an insider.</p>
      </div>
      <div style={sx("display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:baseline;margin-bottom:28px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384;letter-spacing:.1em")}>
        <span data-testid="memory-count">{mem.wallets} WALLETS · {mem.records} RECORDS · {mem.multi_case_wallets} SEEN IN 2+ CASES · {mem.custodians} LIKELY CUSTODIANS</span>
        <button data-testid="memory-toggle" onClick={() => setAll((a) => !a)} style={sx("background:none;border:1px solid #4a463f;color:#e8e2d4;padding:5px 10px;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer")}>{all ? `Show the ${featured.length} repeat wallets only` : `Show all ${mem.items.length}`}</button>
      </div>
      <div style={sx("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr));gap:28px")}>
        {shown.map((m, i) => {
          const r = role(m);
          const tokens = m.tokens.join(", ") || m.cases.map((c) => symbolOf(c) || c).join(", ");
          const note = m.custodian_notes[0]?.note?.split(m.wallet).join(shortAddr(m.wallet))
            ?? `Seen as ${m.roles.join(" and ") || "a wallet"} in ${m.cases.map((c) => symbolOf(c) || c).join(", ")}${Object.values(m.verdicts).length ? ` (verdict ${[...new Set(Object.values(m.verdicts))].join(", ")})` : ""}.`;
          return (
            <div key={m.wallet} data-wallet={m.wallet} style={sx(`background:#f6f2e8;background-image:repeating-linear-gradient(#f6f2e8 0 27px,#c9d3e0 27px 28px);background-position:0 54px;color:#1a1814;padding:16px 22px 22px;border-top:3px solid #b0463a;rotate:${ROT[(i + 1) % 5]};box-shadow:0 12px 26px rgba(0,0,0,.4);display:flex;flex-direction:column;gap:6px;min-width:0`)}>
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#5e574b;display:flex;justify-content:space-between;gap:8px")}><span>PREVIOUSLY SEEN</span><span>IDX {String(i + 1).padStart(3, "0")}</span></div>
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:20px;margin-top:4px")}><Addr value={m.wallet} buttonStyle="background:none;border:1px solid #5e574b;color:#1a1814;padding:2px 7px;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer" /></div>
              <div style={sx("font-size:18px")}>{m.case_count} case{m.case_count === 1 ? "" : "s"} · {tokens}</div>
              <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}><span title={r.tip} style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;border:1.5px solid #3d5a86;color:#3d5a86;padding:2px 7px;cursor:help")}>{r.role}</span></div>
              <div style={sx("font-size:17px;font-style:italic;line-height:1.35;color:#3e382f;overflow-wrap:anywhere")}>{note}</div>
            </div>
          );
        })}
      </div>
      {!shown.length && <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:12px;color:#9a9384")}>{mem.note || "No wallets in desk memory yet."}</div>}
    </main>
  );
}
