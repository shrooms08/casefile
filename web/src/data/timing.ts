// Replay timing, identical to the server (casefile/server/app.py replay_stream):
// each gap between consecutive events is (Δts / speed) seconds, capped at 2.5 s.
export const SPEEDS = [1, 4, 16] as const;
export const MAX_GAP_S = 2.5;

export function tsSeconds(ts: string | null | undefined): number | null {
  if (!ts) return null;
  const t = Date.parse(ts);
  return Number.isNaN(t) ? null : t / 1000;
}

/** Wall-clock seconds to wait before showing `next`, given the event shown before it. */
export function replayDelay(prevTs: string | null | undefined, nextTs: string | null | undefined, speed: number): number {
  const a = tsSeconds(prevTs);
  const b = tsSeconds(nextTs);
  if (a == null || b == null) return 0;
  return Math.min(Math.max(b - a, 0) / speed, MAX_GAP_S);
}
