// Display helpers. Everything formats values that came from the API; nothing is invented here.

export const RED = "#8b1e17", GREEN = "#2e5b39", ORANGE = "#b0521c", OCHRE = "#94690f", BLUE = "#3d5a86";
export const OCH_TAB = "#a87a26", RED_TAB = "#9c3328";
export const ROT = ["-1.2deg", ".8deg", "-.5deg", "1.3deg", "-.9deg"];

const LABEL_COLOR: Record<string, string> = { RUGGED: RED, HIGH_RISK: ORANGE, CAUTION: OCHRE, NO_RUG_EVIDENCE: GREEN };
const LABEL_TAB: Record<string, string> = { RUGGED: RED_TAB, HIGH_RISK: OCH_TAB, CAUTION: BLUE, NO_RUG_EVIDENCE: BLUE };

export const labelText = (l: string | null | undefined) => (l ? l.replace(/_/g, " ") : "PENDING");
export const labelColor = (l: string | null | undefined) => (l && LABEL_COLOR[l]) || "#56606b";
export const labelTab = (l: string | null | undefined) => (l && LABEL_TAB[l]) || "#3e382f";

/** Casefile flags a rug (or high risk) where RugCheck's own flag says not rugged, or the reverse. */
export function disagrees(rugged: boolean | null | undefined, label: string | null | undefined): boolean {
  if (rugged == null || !label) return false;
  const flagged = label === "RUGGED" || label === "HIGH_RISK";
  return rugged !== flagged;
}

export function modelName(id: string | null | undefined): string {
  if (!id) return "";
  const s = id.toLowerCase();
  if (s.includes("nemotron-3.5-lightning")) return "Nemotron 3.5 Lightning · fast";
  if (s.includes("nemotron-3.5-super")) return "Nemotron 3.5 Super · deep";
  return id.split("/").pop() || id;
}
export const modelShort = (id: string | null | undefined) => modelName(id).split(" · ")[0];

export function shortAddr(a: string | null | undefined): string {
  if (!a) return "";
  return a.length > 12 ? `${a.slice(0, 4)}…${a.slice(-4)}` : a;
}

export function clock(s: number): string {
  const v = Math.max(0, Math.floor(s));
  return `${String(Math.floor(v / 60)).padStart(2, "0")}:${String(v % 60).padStart(2, "0")}`;
}

export function duration(s: number | null | undefined): string {
  if (s == null) return "—";
  const v = Math.round(s);
  return `${Math.floor(v / 60)} min ${String(v % 60).padStart(2, "0")} s`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function date(iso: string | null | undefined | Date): string {
  if (!iso) return "—";
  const d = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
export function timeUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

export function usd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: abs >= 100 ? 0 : 2 })}`;
}
export function pct(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}
export function signedPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n < 0 ? "−" : n > 0 ? "+" : ""}${Math.abs(n).toFixed(2)}%`;
}
export const int = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-US"));

export function host(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function value(v: unknown): string {
  if (v == null) return "null";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-US") : String(v);
  if (Array.isArray(v)) return v.length ? v.join(", ") : "[] (none)";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function today(): string {
  return date(new Date()).toUpperCase();
}
