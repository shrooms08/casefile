import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { data } from "./data";
import type { CaseMeta, Health } from "./data";
import { sx } from "./lib/sx";
import { today } from "./lib/format";
import Shelf from "./components/Shelf";
import BoardPage from "./components/Board";
import VerdictPage from "./components/Verdict";
import MemoryPage from "./components/Memory";

interface Ctx {
  health: Health | null;
  cases: CaseMeta[] | null;
  reloadCases: () => void;
  setTopRight: (s: string | null) => void;
  lastCase: string | null;
  setLastCase: (id: string) => void;
}
const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

export const isLive = (h: Health | null) => h?.mode === "live";
export const isHosted = (h: Health | null) => h?.mode === "static";
export const RUN_IT_LIVE = "https://github.com/shrooms08/casefile#run-it-live";

function TopBar({ right }: { right: string }) {
  return (
    <div style={sx("display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:18px clamp(16px,3vw,40px);font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;color:#9a9384;background:#0d0c0b")}>
      <span>CASEFILE</span><span>SOLANA TOKEN INVESTIGATION DESK</span><span data-testid="top-right">{right}</span>
    </div>
  );
}

function Nav() {
  const { health, cases, lastCase } = useApp();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const screen = pathname === "/" ? "home" : pathname.startsWith("/memory") ? "memory"
    : pathname.endsWith("/verdict") ? "verdict" : pathname.startsWith("/case/") ? "board" : "";
  const target = lastCase || cases?.[0]?.case_id || null;
  const navC = (k: string) => (screen === k ? "#e8e2d4" : "transparent");
  const live = isLive(health);
  const btn = (k: string) => `background:none;border:0;border-bottom:1px solid ${navC(k)};color:#e8e2d4;padding:4px 0;cursor:pointer`;
  return (
    <nav style={sx("display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:14px clamp(16px,3vw,40px);border-bottom:1px solid #2c2a26;background:#1a1917")}>
      <div style={sx("display:flex;gap:22px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:12px")}>
        <button onClick={() => nav("/")} style={sx(btn("home"))}>Case shelf</button>
        <button onClick={() => target && nav(`/case/${target}`)} style={sx(btn("board"))}>Case board</button>
        <button onClick={() => target && nav(`/case/${target}/verdict`)} style={sx(btn("verdict"))}>Verdict</button>
        <button onClick={() => nav("/memory")} style={sx(btn("memory"))}>Desk memory</button>
      </div>
      <button onClick={() => nav("/")} style={sx("display:flex;align-items:center;gap:10px;background:none;border:0;color:#e8e2d4;cursor:pointer;padding:0")}>
        <span style={sx("width:38px;height:38px;border:1px solid #e8e2d4;border-radius:50%;display:flex;align-items:center;justify-content:center;font-style:italic;font-size:19px")}>cf</span>
        <span style={sx("font-size:22px;letter-spacing:.01em")}>Casefile</span>
      </button>
      <div data-testid="mode-note" style={sx("display:flex;align-items:center;gap:8px;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#9a9384")}>
        <span style={sx(`width:7px;height:7px;border-radius:50%;background:${live ? "#5f9a6b" : "#d9a24a"}`)}></span>
        {health == null ? "Checking the desk…" : live ? "Live stack connected" : health.mode === "static" ? "Hosted replay" : "Replay-only mode"}
      </div>
    </nav>
  );
}

function Footer() {
  return (
    <footer style={sx("border-top:1px solid #2c2a26;padding:24px clamp(16px,3vw,40px);display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9a9384;letter-spacing:.1em")}>
      <span>CASEFILE · THE AGENT THAT CAN EXPLAIN WHY</span><span>EVIDENCE FROM api.rugcheck.xyz · api.dexscreener.com</span>
    </footer>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [cases, setCases] = useState<CaseMeta[] | null>(null);
  const [topRight, setTopRight] = useState<string | null>(null);
  const [lastCase, setLastCaseState] = useState<string | null>(() => {
    try { return localStorage.getItem("casefile.lastCase"); } catch { return null; }
  });
  const reloadCases = () => { data.cases().then(setCases).catch(() => setCases([])); };
  useEffect(() => {
    data.health().then(setHealth).catch(() => setHealth({ mode: "replay", zetaris: "down", nightshift: "down" }));
    reloadCases();
  }, []);
  const ctx = useMemo<Ctx>(() => ({
    health, cases, reloadCases, setTopRight, lastCase,
    setLastCase: (id) => { setLastCaseState(id); try { localStorage.setItem("casefile.lastCase", id); } catch { /* private mode */ } },
  }), [health, cases, lastCase]);
  return (
    <AppCtx.Provider value={ctx}>
      <div style={sx("min-height:100vh;background:#131210;font-family:'EB Garamond',Georgia,serif")}>
        <TopBar right={topRight ?? today()} />
        <Nav />
        <Routes>
          <Route path="/" element={<Shelf />} />
          <Route path="/case/:caseId" element={<BoardPage />} />
          <Route path="/case/:caseId/verdict" element={<VerdictPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="*" element={<Shelf />} />
        </Routes>
        <Footer />
      </div>
    </AppCtx.Provider>
  );
}
