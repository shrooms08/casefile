import { useState } from "react";
import type { CaseDetail } from "../data";
import type { Board } from "../board/reducer";
import { sx } from "../lib/sx";
import { BLUE, OCHRE, OCH_TAB, RED, RED_TAB, ROT, host, int, pct, shortAddr, signedPct, timeUtc, usd } from "../lib/format";

const TABS: [string, string, string][] = [["holders", "Holders", BLUE], ["liquidity", "Liquidity", OCH_TAB], ["risks", "Risks", RED_TAB], ["sources", "Sources", "#3e382f"]];
const HOLDER_ROT = ["-.6deg", ".5deg", "-.3deg"];   // the design's holder-card tilts
const TIPS: Record<string, string> = {
  AMM: "Automated market maker: a trading-pool program, not a person.",
  LOCKER: "A locker program holding tokens on a schedule, not an owner.",
  CREATOR: "The wallet that deployed the token.",
  custodian: "An exchange or wallet provider holding tokens for many users (from desk memory).",
  network: "Wallets linked by funding or timing, treated as one holder.",
  none: "No label in RugCheck's known accounts.",
};

export default function EvidencePocket({ detail, board }: { detail: CaseDetail | null; board: Board }) {
  const [tab, setTab] = useState("holders");
  const s = detail?.summary;
  const custodians = new Set<string>(board.memory?.detail?.custodian_wallets || []);
  const card = "background:#f6f1e6;padding:12px;display:flex;flex-direction:column;gap:6px;box-shadow:0 3px 8px rgba(0,0,0,.15)";
  const bp = s?.best_pair;
  const vtl = s?.computed?.volume_to_liquidity_24h;
  return (
    <aside data-testid="evidence-pocket" style={sx("flex:1 1 320px;max-width:440px;min-width:0;position:sticky;top:16px")}>
      <div style={sx("display:flex;gap:3px;padding-left:10px;flex-wrap:wrap")}>
        {TABS.map(([k, l, c]) => (
          <button key={k} data-tab={k} onClick={() => setTab(k)} style={sx(`background:${c};color:#f3eee3;border:0;padding:8px 12px ${tab === k ? "10px" : "6px"};border-radius:6px 6px 0 0;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.06em;cursor:pointer;margin-top:${tab === k ? "0px" : "4px"}`)}>{l}</button>
        ))}
      </div>
      <div style={sx("background:#d9cfba;color:#1a1814;padding:0 0 16px;box-shadow:0 14px 34px rgba(0,0,0,.4)")}>
        <div style={sx("background:#cbbfa6;padding:10px 16px;font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.12em;color:#3e382f;clip-path:polygon(0 0,100% 0,100% 70%,50% 100%,0 70%);padding-bottom:18px")}>EVIDENCE POCKET · SNAPSHOT {timeUtc(s?.captured_at?.first).toUpperCase()}</div>
        <div style={sx("padding:10px 14px 0;display:flex;flex-direction:column;gap:10px")}>
          {!s && <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#3e382f")}>The evidence file appears once the case is opened.</div>}
          {s && tab === "holders" && <>
            {s.top_holders.map((h, i) => {
              const custodian = custodians.has(h.owner);
              const badge = h.label ?? (custodian ? "likely custodian" : "unlabelled");
              const tip = h.label_type ? TIPS[h.label_type] ?? h.label_type : custodian ? TIPS.custodian : TIPS.none;
              return (
                <div key={h.owner + i} style={sx(`${card};rotate:${HOLDER_ROT[i % 3]}`)}>
                  <div style={sx("display:flex;justify-content:space-between;gap:8px;align-items:baseline")}><span title={h.owner} style={sx("font-size:17px")}>{shortAddr(h.owner)}</span><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600")}>{pct(h.pct)}</span></div>
                  <div style={sx("display:flex;gap:6px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:10px")}>
                    <span title={tip} style={sx("border:1px solid #1a1814;padding:1px 6px;cursor:help")}>{badge}</span>
                    {custodian && h.label && <span title={TIPS.custodian} style={sx("border:1px solid #3d5a86;color:#3d5a86;padding:1px 6px;cursor:help")}>likely custodian</span>}
                    <span style={sx(`padding:1px 6px;background:${h.insider ? RED : "#56606b"};color:#f6f1e6`)}>{h.insider ? "INSIDER" : "NOT FLAGGED INSIDER"}</span>
                    <span style={sx("color:#5e574b")}>of supply</span>
                  </div>
                </div>
              );
            })}
            {s.insider_networks.count > 0 && (
              <div style={sx(`${card};rotate:.5deg`)}>
                <div style={sx("display:flex;justify-content:space-between;gap:8px;align-items:baseline")}><span style={sx("font-size:17px")}>Insider networks, combined</span><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600")}>{s.insider_networks.supply_pct == null ? "unreliable" : pct(s.insider_networks.supply_pct)}</span></div>
                <div style={sx("display:flex;gap:6px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:10px")}>
                  <span title={TIPS.network} style={sx("border:1px solid #1a1814;padding:1px 6px;cursor:help")}>{s.insider_networks.count} networks · {int(s.insider_networks.accounts)} wallets</span>
                  {s.insider_networks.largest_supply_pct != null && <span style={sx(`padding:1px 6px;background:${RED};color:#f6f1e6`)}>LARGEST {pct(s.insider_networks.largest_supply_pct)}</span>}
                  <span style={sx("color:#5e574b")}>of supply</span>
                </div>
              </div>
            )}
            <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;color:#3e382f")}>{int(s.holders)} holders in total · source api.rugcheck.xyz</div>
          </>}
          {s && tab === "liquidity" && (
            <div style={sx("background:#f6f1e6;padding:14px;display:flex;flex-direction:column;gap:8px;box-shadow:0 3px 8px rgba(0,0,0,.15)")}>
              {([
                ["Best pair", bp ? `${bp.dex}${bp.quote_symbol ? ` · ${bp.quote_symbol}` : ""}` : "—", "The trading pool with the most money in it.", "#1a1814"],
                ["Liquidity", usd(bp?.liquidity_usd), "Money in the pool that holders can sell against.", (bp?.liquidity_usd ?? Infinity) < 10000 ? RED : "#1a1814"],
                ["24h price change", signedPct(bp?.price_change_24h), "Change over the last 24 hours.", (bp?.price_change_24h ?? 0) <= -50 ? RED : "#1a1814"],
                ["24h volume", usd(bp?.volume_24h), "Value traded in the last 24 hours.", "#1a1814"],
                ["Volume ÷ liquidity", vtl == null ? "—" : `${vtl}x`, "How many times the pool’s money changed hands in a day.", (vtl ?? 0) > 100 ? RED : "#1a1814"],
                ["Pairs on DexScreener", int(s.pair_count), "Pools trading this token as the base asset.", "#1a1814"],
              ] as [string, string, string, string][]).map(([k, v, tip, color]) => (
                <div key={k} style={sx("display:flex;justify-content:space-between;gap:10px;border-bottom:1px dotted #bfb39b;padding-bottom:6px")}><span title={tip} style={sx("font-size:16px;cursor:help")}>{k}</span><span style={sx(`font-family:'IBM Plex Mono',monospace;font-size:13px;color:${color}`)}>{v}</span></div>
              ))}
              <div style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b")}>source api.dexscreener.com</div>
            </div>
          )}
          {s && tab === "risks" && <>
            {[...s.risks.map((r) => ({ name: r.name, level: r.level.toUpperCase(), color: r.level === "danger" ? RED : OCHRE, src: `risks${r.value ? ` · ${r.value}` : ""} · api.rugcheck.xyz`, tip: r.description || "" })),
              { name: "RugCheck “rugged” flag", level: s.rugcheck.rugged ? "TRUE" : "FALSE", color: s.rugcheck.rugged ? RED : "#56606b", src: "summary.rugged · api.rugcheck.xyz", tip: "RugCheck's own rug flag." },
              { name: "Mint authority", level: s.authorities.mint_authority ? "ACTIVE" : "NONE", color: s.authorities.mint_authority ? RED : "#56606b", src: "summary.mint_authority · api.rugcheck.xyz", tip: "Can new tokens still be minted?" },
              { name: "Freeze authority", level: s.authorities.freeze_authority ? "ACTIVE" : "NONE", color: s.authorities.freeze_authority ? RED : "#56606b", src: "summary.freeze_authority · api.rugcheck.xyz", tip: "Can holders' tokens be frozen?" },
            ].map((r) => (
              <div key={r.name} title={r.tip} style={sx("background:#f6f1e6;padding:12px;display:flex;justify-content:space-between;gap:10px;align-items:center;box-shadow:0 3px 8px rgba(0,0,0,.15)")}>
                <div style={sx("display:flex;flex-direction:column;gap:2px;min-width:0")}><span style={sx("font-size:17px")}>{r.name}</span><span style={sx("font-family:'IBM Plex Mono',monospace;font-size:10px;color:#5e574b;word-break:break-word")}>{r.src}</span></div>
                <span style={sx(`border:2.5px solid ${r.color};color:${r.color};padding:3px 8px;font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:12px;letter-spacing:.1em;rotate:-4deg`)}>{r.level}</span>
              </div>
            ))}
          </>}
          {s && tab === "sources" && s.sources.map((x, i) => (
            <div key={x.zetaris_view} style={sx(`background:#ecdfae;padding:10px 12px;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.5;rotate:${ROT[i % 5]};box-shadow:0 3px 8px rgba(0,0,0,.15);word-break:break-all`)}>
              <div style={sx("font-size:9px;letter-spacing:.14em;color:#5e574b")}>ZETARIS VIEW ← ORIGINAL API</div>
              <div>{x.zetaris_view}</div>
              <div style={sx("color:#5e574b")}>← <a href={x.api_url} target="_blank" rel="noreferrer" style={sx("color:#5e574b")} title={x.api_url}>{host(x.api_url)}</a></div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
