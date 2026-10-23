// The case board as a pure fold over normalized trace events (docs/TRACE_SCHEMA.md).
// Live streams and replays both render through reduceBoard(events): it only looks at
// events already shown, never at future ones.
import type { TraceEvent } from "../data/types";

export type Stamp = "UNVERIFIED" | "ACCEPTED" | "REJECTED";
export const LANES = ["holders", "liquidity", "deployer"] as const;
export type LaneKey = (typeof LANES)[number];

export interface Sheet {
  text: string;
  model: string | null;
  receipt: string | null;
  seq: number;
  status: Stamp;
  note?: string;
  verified?: string;
}

export interface ClaimCard extends Sheet {
  id: string;
  lane: string;
  ts: string;
  reworkRequested?: string;
  rev?: Sheet;
  dropped?: string;
}

export interface Board {
  events: TraceEvent[];
  opened?: TraceEvent;
  memory?: TraceEvent;
  plan?: TraceEvent;
  verdict?: TraceEvent;
  started: Partial<Record<LaneKey, TraceEvent>>;
  claims: ClaimCard[];
  acts: Record<string, TraceEvent[]>;   // per agent: investigator_started, sql_query, retry, fallback, error
  skepticLog: TraceEvent[];             // decisions, reworks, drops, skeptic retries/fallbacks
  errors: TraceEvent[];
  decisions: number;
}

const stamp = (d: string | undefined): Stamp => (d === "accept" ? "ACCEPTED" : d === "reject" ? "REJECTED" : "UNVERIFIED");

export function reduceBoard(events: TraceEvent[]): Board {
  const b: Board = { events, started: {}, claims: [], acts: {}, skepticLog: [], errors: [], decisions: 0 };
  const byId = new Map<string, ClaimCard>();
  const act = (e: TraceEvent) => {
    const k = e.agent || "casefile";
    (b.acts[k] ||= []).push(e);
  };
  for (const e of events) {
    const d = e.detail || {};
    switch (e.type) {
      case "case_opened": b.opened = e; break;
      case "memory_recalled": b.memory = e; break;
      case "plan": b.plan = e; break;
      case "investigator_started":
        if (e.agent && (LANES as readonly string[]).includes(e.agent)) b.started[e.agent as LaneKey] = e;
        act(e);
        break;
      case "sql_query": act(e); break;
      case "claim": {
        const prior = byId.get(d.id);
        const sheet: Sheet = { text: d.claim, model: e.model, receipt: e.receipt_id, seq: e.seq, status: "UNVERIFIED",
                               verified: d.evidence_verified };
        if (prior && d.revision_of) {
          prior.rev = sheet;
        } else {
          const card: ClaimCard = { ...sheet, id: d.id, lane: e.agent || "", ts: e.ts };
          byId.set(d.id, card);
          b.claims.push(card);
        }
        break;
      }
      case "skeptic_decision": {
        b.decisions += 1;
        b.skepticLog.push(e);
        const card = byId.get(d.id);
        if (!card) break;
        const target: Sheet = d.round === "re_review" && card.rev ? card.rev : card;
        target.status = stamp(d.decision);
        target.note = d.reason;
        break;
      }
      case "rework_requested": {
        b.skepticLog.push(e);
        const card = byId.get(d.id);
        if (card) card.reworkRequested = d.fix_request;
        break;
      }
      case "claim_dropped": {
        b.skepticLog.push(e);
        const card = byId.get(d.id);
        if (card) card.dropped = d.why || "dropped";
        break;
      }
      case "retry":
      case "fallback":
        if (e.agent === "skeptic") b.skepticLog.push(e);
        else act(e);
        break;
      case "error":
        b.errors.push(e);
        act(e);
        break;
      case "verdict": b.verdict = e; break;
    }
  }
  return b;
}

export type LaneState = { now: string; working: boolean; started: boolean; lastTs: string | null; model: string | null };

/** What a lane is doing, from the events shown so far only. */
export function laneState(b: Board, key: LaneKey): LaneState {
  const acts = b.acts[key] || [];
  const claims = b.claims.filter((c) => c.lane === key);
  const mine = [...acts, ...claims.map((c) => ({ ts: c.ts, model: c.model, type: "claim" }))].sort((x, y) => (x.ts < y.ts ? -1 : 1));
  const last = mine[mine.length - 1] as { ts: string; model: string | null; type: string } | undefined;
  const model = [...mine].reverse().find((x) => x.model)?.model ?? null;
  const started = !!b.started[key] || mine.length > 0;
  const failed = acts.find((a) => a.type === "error");
  const base = { started, lastTs: last?.ts ?? null, model };
  if (!b.plan || !started) return { ...base, now: "Waiting for the plan", working: false };
  if (failed) return { ...base, now: "Stopped: " + failed.title.replace(/^[^:]*:\s*/, ""), working: false };
  if (!claims.length) {
    return { ...base, now: last?.type === "retry" ? "Waiting on the model provider…" : "Writing up claims…", working: !b.verdict };
  }
  if (claims.some((c) => !c.dropped && (c.status === "UNVERIFIED" || c.rev?.status === "UNVERIFIED"))) {
    return { ...base, now: "Waiting on the Skeptic…", working: !b.verdict };
  }
  if (claims.some((c) => c.reworkRequested && !c.rev && !c.dropped)) {
    return { ...base, now: "Reworking the rejected claim…", working: !b.verdict };
  }
  return { ...base, now: "Finished", working: false };
}

export function pendingReviews(b: Board): number {
  return b.claims.filter((c) => !c.dropped && (c.status === "UNVERIFIED" || c.rev?.status === "UNVERIFIED")).length;
}
