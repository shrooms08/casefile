// UI check against the static build (no backend). Run from the repo root:
//   cd web && npm run build:static && cd .. && node scripts/ui_check.mjs            (serves web/dist itself)
//   node scripts/ui_check.mjs --url http://localhost:4173                         (e.g. against `vite preview`)
// With Playwright (preinstalled Chromium):
//   - opens /, each of the 4 cases (replay at 16x to the verdict), each verdict page, /memory
//   - fails on console errors, on "TJ3" / "CF_1" / any mock id from the design export
//   - checks the ヤギ verdict shows exactly the why-lines in its verdict.json
//   - screenshots at 1440 and 390 wide into web/screenshots/, and checks no horizontal scroll at 390
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFileSync, existsSync, mkdirSync, statSync } from "node:fs";
import { extname, join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(ROOT, "web", "package.json"));
const { chromium } = require("playwright");
const DIST = join(ROOT, "web", "dist");
const urlArg = process.argv.indexOf("--url");
const EXTERNAL = urlArg > 0 ? process.argv[urlArg + 1].replace(/\/$/, "") : null;
const SHOTS = join(ROOT, "web", "screenshots");
const CASES = ["m_bd95541d260d", "m_0c961a12701d", "m_d54bf9a14eb4", "m_d2f031d73387"];
const YAGI = "m_bd95541d260d";
// Mock values from design/src/index.html that must never ship.
const FORBIDDEN = ["TJ3", "CF_1", "run_0a7e2f", "m_4a1c07e93b2f", "m_e05d7718ac44", "m_71bb2c9d0f15", "7nYa…pump", "9kMc…pump"];
const MOCK_RECEIPT = /\brcpt_[0-9a-f]{6}\b/;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".jsonl": "application/x-ndjson" };

if (!EXTERNAL && !existsSync(join(DIST, "index.html"))) {
  console.error("web/dist is missing: run `cd web && npm run build:static` first");
  process.exit(2);
}
mkdirSync(SHOTS, { recursive: true });

const server = createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url, "http://x").pathname);
  let file = join(DIST, path);
  if (!file.startsWith(DIST) || !existsSync(file) || statSync(file).isDirectory()) file = join(DIST, "index.html");
  res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
  res.end(readFileSync(file));
});
if (!EXTERNAL) await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = EXTERNAL ?? `http://127.0.0.1:${server.address().port}`;
console.log(`UI check against ${BASE}`);

const failures = [];
const fail = (m) => { failures.push(m); console.log("  FAIL " + m); };
const ok = (m) => console.log("  ok   " + m);
const browser = await chromium.launch();

async function forbiddenCheck(page, where) {
  const text = await page.evaluate(() => document.body.innerText + "\n" + document.title);
  const hits = FORBIDDEN.filter((f) => text.includes(f));
  if (MOCK_RECEIPT.test(text)) hits.push(text.match(MOCK_RECEIPT)[0]);
  if (hits.length) fail(`${where}: shows mock/filler text ${JSON.stringify(hits)}`);
}

async function run(width) {
  const ctx = await browser.newContext({ viewport: { width, height: width > 600 ? 1000 : 844 }, reducedMotion: "no-preference" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = (name) => page.screenshot({ path: join(SHOTS, `${name}-${width}.png`), fullPage: true });
  const noHScroll = async (where) => {
    if (width > 600) return;
    const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
    if (sw > cw) fail(`${where} @${width}: horizontal scroll (scrollWidth ${sw} > ${cw})`); else ok(`${where} @${width}: no horizontal scroll`);
  };
  console.log(`\n== ${width}px`);

  await page.goto(BASE + "/");
  await page.waitForSelector("[data-case]");
  const shelf = await page.$$eval("[data-case]", (els) => els.map((e) => e.getAttribute("data-case")));
  if (CASES.every((c) => shelf.includes(c))) ok(`shelf lists ${shelf.length} cases`); else fail(`shelf cases ${shelf}`);
  await page.waitForFunction(() => !/Checking/.test(document.querySelector("[data-testid=mode-note]")?.textContent || "Checking"));
  const mode = (await page.textContent("[data-testid=mode-note]")).trim();
  if (mode === "Hosted replay") ok("mode note: Hosted replay"); else fail(`mode note: "${mode}"`);
  const liveHref = await page.getAttribute("[data-testid=live-note] a", "href");
  if (liveHref === "https://github.com/shrooms08/casefile#run-it-live") ok("disabled note links to the README run-it-live section");
  else fail(`live note link: ${liveHref}`);
  if (await page.isDisabled("#mint")) ok("new-case input disabled in static mode"); else fail("input enabled in static mode");
  const strip = await page.$$eval("[data-testid=rugcheck-strip]", (els) => els.map((e) => e.innerText));
  ok(`rugcheck strips on shelf: ${strip.length}`);
  await forbiddenCheck(page, "shelf");
  await noHScroll("shelf");
  await shot("shelf");

  for (const cid of CASES) {
    await page.goto(`${BASE}/case/${cid}`);
    await page.waitForSelector("[data-testid=speed-16]");
    await page.click("[data-testid=speed-16]");
    const t0 = Date.now();
    await page.waitForSelector("[data-testid=board-verdict]", { timeout: 180000 });
    await page.waitForFunction(() => /^Case closed/.test(document.querySelector("[data-testid=now-line]")?.textContent || ""), null, { timeout: 30000 });
    const step = await page.textContent("[data-testid=step-counter]");
    const pill = (await page.textContent("[data-testid=mode-pill]")).trim();
    if (pill !== "HOSTED REPLAY") fail(`board ${cid}: mode pill "${pill}"`);
    const top = await page.textContent("[data-testid=top-right]");
    ok(`board ${cid}: replay 16x reached the verdict in ${((Date.now() - t0) / 1000).toFixed(1)} s · ${step} · top bar "${top}"`);
    if (!/^RUN \w+ · SEQ (\d+)\/\1$/.test(top)) fail(`board ${cid}: top bar should read RUN <id> · SEQ N/N, got "${top}"`);
    for (const tab of ["liquidity", "risks", "sources", "holders"]) await page.click(`[data-tab=${tab}]`);
    await forbiddenCheck(page, `board ${cid}`);
    await noHScroll(`board ${cid}`);
    if (cid === YAGI || width > 600) await shot(`board-${cid}`);

    await page.goto(`${BASE}/case/${cid}/verdict`);
    await page.waitForSelector("[data-testid=why-lines] li");
    const shownWhy = await page.$$eval("[data-testid=why-text]", (els) => els.map((e) => e.textContent.trim()));
    const v = JSON.parse(readFileSync(join(ROOT, "demo_cases", cid, "verdict.json"), "utf-8")).verdict;
    const expected = v.why.map((w) => w.sentence.trim());
    if (JSON.stringify(shownWhy) === JSON.stringify(expected)) ok(`verdict ${cid}: exactly ${expected.length} why-lines from verdict.json`);
    else fail(`verdict ${cid}: why-lines differ\n    shown ${JSON.stringify(shownWhy)}\n    want  ${JSON.stringify(expected)}`);
    if ((await page.textContent("[data-testid=one-line]")).trim() !== v.one_line.trim()) fail(`verdict ${cid}: one_line differs`);
    if ((await page.textContent("[data-testid=change-mind]")).trim() !== v.what_would_change_my_mind.trim()) fail(`verdict ${cid}: change-my-mind differs`);
    const whyText = await page.textContent("[data-testid=why-lines]");
    // The contrast strip must not be a why-line (real sentences may still mention RugCheck's risk list).
    if (/RugCheck: (not )?rugged|Casefile: /.test(whyText) || await page.$("[data-testid=why-lines] [data-testid=rugcheck-strip]"))
      fail(`verdict ${cid}: the RugCheck contrast strip appears inside the why-lines`);
    const stripAbove = await page.$("[data-testid=rugcheck-strip]");
    const meta = JSON.parse(readFileSync(join(ROOT, "demo_cases", cid, "meta.json"), "utf-8"));
    const shouldShow = meta.rugcheck_rugged === false && ["RUGGED", "HIGH_RISK"].includes(meta.label);
    if (!!stripAbove !== shouldShow) fail(`verdict ${cid}: contrast strip shown=${!!stripAbove}, expected ${shouldShow}`);
    else ok(`verdict ${cid}: contrast strip ${shouldShow ? "shown above the sheet" : "not shown"} (rugcheck_rugged=${meta.rugcheck_rugged}, ${meta.label})`);
    const chips = await page.$$("[data-chip]");
    if (chips.length) { await chips[0].click(); ok(`verdict ${cid}: ${chips.length} citation chips, pinned the first`); }
    await forbiddenCheck(page, `verdict ${cid}`);
    await noHScroll(`verdict ${cid}`);
    if (cid === YAGI || width > 600) await shot(`verdict-${cid}`);
  }

  // Deep links: direct HTTP GET, a fresh tab straight onto the URL, then a hard refresh.
  for (const [path, sel] of [[`/case/${YAGI}/verdict`, "[data-testid=why-lines] li"], ["/memory", "[data-wallet]"], [`/case/${YAGI}`, "[data-testid=step-counter]"]]) {
    const res = await fetch(BASE + path);
    const html = await res.text();
    if (res.status !== 200 || !html.includes('<div id="root">')) { fail(`deep link ${path}: HTTP ${res.status}`); continue; }
    const tab = await ctx.newPage();
    tab.on("pageerror", (e) => errors.push(String(e)));
    await tab.goto(BASE + path);
    await tab.waitForSelector(sel, { timeout: 30000 });
    await tab.reload({ waitUntil: "load" });
    await tab.waitForSelector(sel, { timeout: 30000 });
    ok(`deep link ${path}: HTTP 200, renders on direct open and after hard refresh`);
    if (path.endsWith("/verdict")) {
      await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
      await tab.click("[data-testid=share]");
      await tab.waitForFunction(() => /Link copied/.test(document.querySelector("[data-testid=share]")?.textContent || ""), null, { timeout: 5000 }).catch(() => {});
      const copied = await tab.evaluate(() => navigator.clipboard.readText()).catch((e) => `read failed: ${e}`);
      if (copied === tab.url()) ok(`share link copies the absolute URL: ${copied}`); else fail(`share link copied "${copied}", page is ${tab.url()}`);
    }
    await tab.close();
  }

  await page.goto(BASE + "/memory");
  await page.waitForSelector("[data-wallet]");
  const nFeatured = (await page.$$("[data-wallet]")).length;
  await shot("memory");
  await page.click("[data-testid=memory-toggle]");
  const nAll = (await page.$$("[data-wallet]")).length;
  if (nAll > nFeatured) ok(`memory: ${nFeatured} repeat wallets first, ${nAll} with show all`); else fail(`memory toggle ${nFeatured} -> ${nAll}`);
  await forbiddenCheck(page, "memory");
  await noHScroll("memory");

  if (errors.length) fail(`${width}px console errors: ${JSON.stringify(errors.slice(0, 5))}`); else ok(`${width}px: no console errors`);
  await ctx.close();
}

try {
  await run(1440);
  await run(390);
} finally {
  await browser.close();
  if (!EXTERNAL) server.close();
}
console.log(failures.length ? `\nUI CHECK FAILED (${failures.length})` : "\nUI CHECK PASSED");
process.exit(failures.length ? 1 : 0);
