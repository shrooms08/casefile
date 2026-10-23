import { useState } from "react";
import { sx } from "../lib/sx";
import { labelText, shortAddr } from "../lib/format";

/** "RugCheck: not rugged → Casefile: RUGGED" (design shelf strip), from meta.rugcheck_rugged and the label. */
export function RugcheckStrip({ rugged, label }: { rugged: boolean | null; label: string | null }) {
  return (
    <div data-testid="rugcheck-strip" style={sx("font-family:'IBM Plex Mono',monospace;font-size:11px;padding:8px 10px;background:#1a1814;color:#efe9dc;display:flex;gap:6px;flex-wrap:wrap")}>
      <span>RugCheck: {rugged ? "rugged" : "not rugged"}</span><span>→</span><span style={sx("color:#e58a7f")}>Casefile: {labelText(label)}</span>
    </div>
  );
}

/** first4…last4 with a copy button for the full address. */
export function Addr({ value, style, buttonStyle }: { value: string; style?: string; buttonStyle?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(value).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };
  return (
    <span style={sx("display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap")}>
      <span title={value} style={style ? sx(style) : undefined}>{shortAddr(value)}</span>
      <button onClick={copy} aria-label={`Copy ${value}`}
        style={sx(buttonStyle ?? "background:none;border:1px solid #4a463f;color:inherit;padding:3px 8px;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer")}>
        {copied ? "Copied" : "Copy"}</button>
    </span>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <main style={sx("max-width:1440px;margin:0 auto;padding:28px clamp(16px,3vw,48px) 80px;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#9a9384")}>
      {what}
    </main>
  );
}
