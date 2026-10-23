// JSON-in / JSON-out bridge for Python: `tsx cli.ts <op> <persistDir>` with the request on stdin.
// Ops: recall {wallets:[...]}, store {case_id, mint, symbol, established, verdict, wallets:[...]},
//      history {memory_id}, stats {}, sleep_preview {}.
// Persistence is explicit (the persistDir argument); index.ts never reads the environment.

import { HMEM } from "./index.ts";
import { CasefileMemory } from "./casefile.ts";

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString("utf-8");
}

async function main(): Promise<void> {
  const [op, persistDir] = process.argv.slice(2);
  if (!op || !persistDir) throw new Error("usage: tsx cli.ts <op> <persistDir>");
  const raw = await readStdin();
  const req = raw.trim() ? JSON.parse(raw) : {};
  const mem = new CasefileMemory(new HMEM({ persistDir, actor: "casefile" }));
  let result: unknown;
  switch (op) {
    case "recall": result = mem.recallWallets(req.wallets ?? []); break;
    case "store": result = mem.storeCase(req); break;
    case "history": result = mem.history(req.memory_id); break;
    case "stats": result = mem.stats(); break;
    case "sleep_preview": result = mem.hmem.sleep.preview(); break;
    default: throw new Error(`unknown op ${op}`);
  }
  process.stdout.write(JSON.stringify({ ok: true, result }) + "\n");
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e?.message ?? e) }) + "\n");
  process.exit(1);
});
