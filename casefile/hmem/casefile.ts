// Casefile's use of H-MEM: wallet memories across investigations.
//
// One record per (wallet, case_id, role). Recall is an exact tag filter on wallet:<addr>
// (a base58 address scores below the default query threshold, so query() is not used),
// then ranked with the spec's own scoring and logged as a "read" like any retrieval.
// Derived memory: a wallet that was a top holder of 2+ different ESTABLISHED tokens gets a
// "likely custodian or exchange" record, created through the dreaming approval boundary
// (proposeRule -> approve, actor casefile:rules) so the ledger shows how it was made.

import { HMEM } from "./index.ts";
import type { MemoryRecord } from "./types.ts";
import { snapshot } from "./memoryStore.ts";

export interface WalletFact {
  wallet: string;
  role: "creator" | "insider" | "holder";
  rank?: number;
  pct?: number;
  label?: string | null;
}

export interface CaseMemoryInput {
  case_id: string;
  mint: string;
  symbol: string;
  established: boolean;
  verdict: string;
  wallets: WalletFact[];
}

const tagValue = (m: MemoryRecord, key: string): string | undefined =>
  m.tags.find((t) => t.startsWith(`${key}:`))?.slice(key.length + 1);

export function recordKey(m: MemoryRecord): string {
  return `${tagValue(m, "wallet")}|${tagValue(m, "case")}|${tagValue(m, "role")}`;
}

function content(c: CaseMemoryInput, w: WalletFact): string {
  // Lower-case words only: the reference entity extractor treats Capitalised words as entities.
  const where = w.role === "holder"
    ? `top holder${w.rank ? ` rank ${w.rank}` : ""}${w.pct != null ? ` at ${w.pct.toFixed(2)} pct` : ""}`
    : w.role;
  const label = w.label ? `, labelled ${w.label.toLowerCase()}` : "";
  return `wallet ${w.wallet} was ${where}${label} of token ${c.symbol.toLowerCase()} (mint ${c.mint}) in case ${c.case_id}; ` +
    `established=${c.established}; verdict ${c.verdict.toLowerCase()}`;
}

export class CasefileMemory {
  constructor(readonly hmem: HMEM) {}

  private live(): MemoryRecord[] {
    return this.hmem.store.all();
  }

  storeCase(c: CaseMemoryInput): { created: string[]; updated: string[]; unchanged: string[]; derived: string[] } {
    const out = { created: [] as string[], updated: [] as string[], unchanged: [] as string[], derived: [] as string[] };
    const byKey = new Map(this.live().filter((m) => m.tags.includes("kind:wallet_fact")).map((m) => [recordKey(m), m]));
    const seen = new Set<string>();
    for (const w of c.wallets) {
      const key = `${w.wallet}|${c.case_id}|${w.role}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const tags = [
        "project:casefile", "kind:wallet_fact", `wallet:${w.wallet}`, `role:${w.role}`, `case:${c.case_id}`,
        `mint:${c.mint}`, `token:${c.symbol.toLowerCase()}`, `established:${c.established}`,
        `verdict:${c.verdict.toLowerCase()}`, ...(w.label ? [`label:${w.label.toLowerCase()}`] : []),
      ];
      const text = content(c, w);
      const prior = byKey.get(key);
      if (!prior) {
        const rec = this.hmem.add({
          content: text, type: "factual", layer: "long_term", tags, confidence: 0.85,
          source: `casefile:verdict:${c.case_id}`, missionId: c.case_id, entities: [w.wallet],
          provenance: { origin: "plan_completion", learnedAt: this.hmem.clock(), label: `verdict for ${c.case_id}`, refs: [c.case_id] },
        });
        out.created.push(rec.id);
      } else if (prior.content !== text || prior.tags.join(",") !== tags.join(",")) {
        this.hmem.store.update(prior.id, { content: text, tags });
        out.updated.push(prior.id);
      } else {
        out.unchanged.push(prior.id);
      }
    }
    out.derived = this.deriveCustodians(c.wallets.filter((w) => w.role === "holder").map((w) => w.wallet));
    this.hmem.store.persist();
    return out;
  }

  // A wallet that is a top holder in 2+ DIFFERENT established tokens (distinct mints).
  deriveCustodians(wallets: string[]): string[] {
    const made: string[] = [];
    for (const wallet of new Set(wallets)) {
      const facts = this.live().filter((m) =>
        m.tags.includes("kind:wallet_fact") && m.tags.includes(`wallet:${wallet}`) &&
        m.tags.includes("role:holder") && m.tags.includes("established:true"));
      const mints = [...new Set(facts.map((m) => tagValue(m, "mint")!))].sort();
      if (mints.length < 2) continue;
      const symbols = [...new Set(facts.map((m) => tagValue(m, "token")!))].sort();
      const existing = this.live().filter((m) =>
        m.tags.includes("derived:custodian") && m.tags.includes(`wallet:${wallet}`) && !m.supersededBy);
      const basis = `mints:${mints.join(",")}`;
      if (existing.some((m) => m.tags.includes(basis))) continue; // same evidence, nothing new
      const proposal = this.hmem.dreaming.proposeRule({
        type: "insight",
        content: `wallet ${wallet} is likely a custodian or exchange: top holder of ${mints.length} different ` +
          `established tokens (${symbols.join(", ")})`,
        derivedFrom: facts.map((m) => m.id).sort(),
      }, ["project:casefile", "derived:custodian", `wallet:${wallet}`, basis]);
      const rec = this.hmem.dreaming.approve(proposal.id);
      if (!rec) continue;
      this.hmem.store.update(rec.id, { entities: [wallet], confidence: 0.8 });
      for (const old of existing) this.hmem.store.update(old.id, { supersededBy: rec.id });
      if (existing.length) this.hmem.store.update(rec.id, { supersedes: existing[0].id });
      made.push(rec.id);
    }
    return made;
  }

  recallWallets(wallets: string[], query = "wallet history"): Record<string, Array<Record<string, unknown>>> {
    const out: Record<string, Array<Record<string, unknown>>> = {};
    for (const wallet of new Set(wallets)) {
      const hits = this.live().filter((m) => m.tags.includes(`wallet:${wallet}`));
      if (!hits.length) continue;
      const ranked = hits
        .map((m) => ({ m, relevance: this.hmem.retrieval.scoreOne(m, `${query} ${wallet}`) }))
        .sort((a, b) => b.relevance - a.relevance || a.m.id.localeCompare(b.m.id));
      out[wallet] = ranked.map(({ m, relevance }) => {
        this.hmem.store.touch(m.id);
        this.hmem.ledger.log(m.id, "read", "casefile:recall", { details: { query: `wallet ${wallet}` } });
        return {
          memory_id: m.id,
          kind: m.tags.includes("derived:custodian") ? "derived:custodian" : "wallet_fact",
          content: m.content,
          role: tagValue(m, "role") ?? null,
          case_id: tagValue(m, "case") ?? null,
          token: tagValue(m, "token") ?? null,
          mint: tagValue(m, "mint") ?? null,
          established: tagValue(m, "established") === undefined ? null : tagValue(m, "established") === "true",
          verdict: tagValue(m, "verdict") ?? null,
          label: tagValue(m, "label") ?? null,
          derived_from: m.derivedFrom ?? null,
          superseded_by: m.supersededBy ?? null,
          confidence: m.confidence,
          relevance: Number(relevance.toFixed(4)),
          layer: m.layer,
        };
      });
    }
    this.hmem.store.persist(); // touch() alone does not persist
    return out;
  }

  history(memoryId: string) {
    return this.hmem.ledger.history(memoryId);
  }

  stats() {
    const all = this.live();
    return {
      records: all.length,
      wallet_facts: all.filter((m) => m.tags.includes("kind:wallet_fact")).length,
      custodian_notes: all.filter((m) => m.tags.includes("derived:custodian") && !m.supersededBy).length,
      ledger: this.hmem.ledger.stats(),
    };
  }
}

export { snapshot };
