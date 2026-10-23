import type { CSSProperties } from "react";

// The design ships inline style strings; sx() turns one into a React style object so the
// markup's CSS is reused verbatim (only the {{ bindings }} become template literals).
const cache = new Map<string, CSSProperties>();

export function sx(style: string): CSSProperties {
  const hit = cache.get(style);
  if (hit) return hit;
  const out: Record<string, string> = {};
  for (const decl of style.split(";")) {
    const i = decl.indexOf(":");
    if (i < 0) continue;
    const prop = decl.slice(0, i).trim();
    const value = decl.slice(i + 1).trim();
    if (!prop) continue;
    const key = prop.startsWith("--") ? prop : prop.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());
    out[key] = value;
  }
  if (cache.size > 5000) cache.clear();
  cache.set(style, out as CSSProperties);
  return out as CSSProperties;
}

export const MONO = "'IBM Plex Mono',monospace";
