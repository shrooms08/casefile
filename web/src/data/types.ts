// Shapes returned by the Casefile API (casefile/server) and mirrored in web/public/demo/.

export type EventType =
  | "case_opened" | "memory_recalled" | "plan" | "investigator_started" | "sql_query" | "claim"
  | "skeptic_decision" | "rework_requested" | "claim_dropped" | "retry" | "fallback" | "verdict" | "error";

export interface TraceEvent {
  seq: number;
  ts: string;
  run_id: string;
  case_id: string;
  type: EventType;
  agent: string | null;
  model: string | null;
  receipt_id: string | null;
  title: string;
  detail: Record<string, any>;
}

export interface DoneMessage {
  type: "done";
  case_id: string;
  run_id: string;
  status?: string;
  summary?: Record<string, any>;
}

export type Mode = "live" | "replay" | "static";

export interface Health {
  mode: Mode;
  zetaris: string;
  nightshift: string;
  investigation_running?: { case_id: string; run_id: string; mint: string; started_at: string } | null;
}

export interface CaseMeta {
  case_id: string;
  run_id: string;
  mint: string;
  symbol: string;
  rugcheck_rugged: boolean | null;
  label: string | null;
  one_line: string | null;
  duration_s: number | null;
  llm_calls: number | null;
  models_used: string[] | null;
  recorded_at: string | null;
  source: "demo" | "runs";
  status?: string;
  runs?: string[];
}

export interface Evidence {
  table: string;
  field: string;
  value: any;
  source_api_url: string | null;
  formula?: string | null;
  source_case?: string | null;
  verified?: boolean;
  check?: string;
}

export interface Claim {
  id: string;
  agent: string;
  claim: string;
  evidence: Evidence[];
  confidence: string;
  innocent_explanation_checked?: string;
  revision_of?: string;
}

export interface VerdictDoc {
  run_id: string;
  case_id: string;
  mint: string;
  symbol: string;
  verdict: {
    label: string;
    one_line: string;
    why: { claim_id: string; sentence: string }[];
    what_would_change_my_mind: string;
    models_used: string[];
  };
  seconds?: number;
  llm_calls?: number;
  accepted_claims: Claim[];
  dropped: { id: string; why: string; claim?: string }[];
}

export interface CaseSummary {
  mint: string;
  symbol: string;
  name?: string;
  rugcheck: { score: number | null; score_normalised: number | null; rugged: boolean | null };
  best_pair: {
    dex: string; quote_symbol?: string; pair_address?: string; url?: string; liquidity_usd: number | null;
    price_change_24h: number | null; volume_24h: number | null; fdv?: number | null; pair_created_at_ms?: number | null;
  } | null;
  pair_count: number;
  holders: number | null;
  top_holders: { owner: string; pct: number; insider: boolean | null; label: string | null; label_type: string | null }[];
  risks: { name: string; level: string; value: string | null; description: string | null }[];
  insider_networks: {
    count: number; largest_size: number; accounts: number; supply_pct: number | null;
    largest_supply_pct: number | null; graph_insiders_detected: number | null;
  };
  creator: { wallet: string | null; balance: number | null };
  authorities: { mint_authority: string | null; freeze_authority: string | null; update_authority: string | null; metadata_mutable: boolean | null };
  established: boolean | null;
  computed: Record<string, any>;
  sources: { kind: string; zetaris_view: string; read_from: string; via: string; api_url: string }[];
  captured_at: { first: string; last: string } | null;
}

export interface CaseDetail {
  meta: CaseMeta;
  verdict: VerdictDoc | null;
  summary: CaseSummary | null;
  runs: string[];
}

export interface TraceDoc {
  case_id: string;
  run_id: string;
  source: string;
  summary: Record<string, any>;
  events: TraceEvent[];
}

export interface MemoryItem {
  wallet: string;
  case_count: number;
  cases: string[];
  roles: string[];
  tokens: string[];
  verdicts: Record<string, string>;
  likely_custodian: boolean;
  custodian_notes: { memory_id: string; note: string; derived_from: string[] }[];
}

export interface MemorySummary {
  records: number;
  wallets: number;
  custodians: number;
  multi_case_wallets: number;
  items: MemoryItem[];
  note?: string;
}

export interface StreamHandlers {
  onEvent: (e: TraceEvent) => void;
  onDone: (d: DoneMessage) => void;
  onError?: (err: string) => void;
}

export class BusyError extends Error {
  constructor(public running: { case_id: string; run_id: string; mint?: string }) {
    super("Another case is being investigated");
  }
}

/** The one interface both data sources implement. Each subscribe call returns a cancel function. */
export interface DataSource {
  kind: "api" | "static";
  health(): Promise<Health>;
  cases(): Promise<CaseMeta[]>;
  caseDetail(caseId: string, run?: string): Promise<CaseDetail>;
  trace(caseId: string, run?: string): Promise<TraceDoc>;
  replay(caseId: string, opts: { speed: number; from: number; run?: string }, h: StreamHandlers): () => void;
  stream(caseId: string, run: string, h: StreamHandlers): () => void;
  investigate(mint: string): Promise<{ case_id: string; run_id: string }>;
  memory(): Promise<MemorySummary>;
}
