import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/fleet-tokens.css";
import {
  AgentCard,
  AgentDialog,
  FleetHeader,
  FleetSidebar,
  LogFeed,
  ScheduleStrip,
  SummonPalette,
} from "../components/fleet/Components.jsx";
import { FLEET_AGENTS, FLEET_TIERS, FLEET_LOG_POOL } from "../data/fleetAgents.js";

const SCHEDULE = [
  { hour: 2,  tier: "delivery", id: "chat-quality-evaluator" },
  { hour: 3,  tier: "enrich",   id: "maker-site-doctor" },
  { hour: 4,  tier: "ingest",   id: "scraper-dispatcher" },
  { hour: 5,  tier: "enrich",   id: "maker-enricher" },
  { hour: 6,  tier: "ingest",   id: "dedupe-sweeper" },
  { hour: 7,  tier: "quality",  id: "price-anomaly-detector" },
  { hour: 9,  tier: "cloud",    id: "aws-cost-sentinel" },
];

function fmtUtc(d) {
  return `${d.getUTCHours().toString().padStart(2,'0')}:${d.getUTCMinutes().toString().padStart(2,'0')}:${d.getUTCSeconds().toString().padStart(2,'0')}`;
}

export default function Agents() {
  const navigate = useNavigate();
  const [agents] = useState(FLEET_AGENTS);
  const [activeTier, setActiveTier] = useState("ALL");
  const [selected, setSelected] = useState(null);
  const [summonOpen, setSummonOpen] = useState(false);
  const [clock, setClock] = useState(() => fmtUtc(new Date()));
  const [logs, setLogs] = useState(() =>
    FLEET_LOG_POOL.slice(0, 6).map((e, i) => ({
      ...e,
      time: `04:${(12 + i).toString().padStart(2,'0')}:${(38 + i*3).toString().padStart(2,'0')}`,
    }))
  );

  useEffect(() => {
    const t = setInterval(() => setClock(fmtUtc(new Date())), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let timer = null;
    const tick = () => {
      const ev = FLEET_LOG_POOL[Math.floor(Math.random() * FLEET_LOG_POOL.length)];
      const time = fmtUtc(new Date());
      setLogs(prev => [...prev.slice(-60), { ...ev, time }]);
    };
    const schedule = () => {
      timer = setTimeout(() => { tick(); schedule(); }, 1800 + Math.random() * 2200);
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { setSelected(null); setSummonOpen(false); }
      if (e.key === "/" && !summonOpen && !selected) {
        e.preventDefault();
        setSummonOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [summonOpen, selected]);

  const filtered = useMemo(() => {
    if (activeTier === "ALL") return agents;
    return agents.filter(a => a.tier === activeTier);
  }, [agents, activeTier]);

  const summary = useMemo(() => ({
    online:   agents.filter(a => a.status === "online").length,
    degraded: agents.filter(a => a.status === "degraded").length,
    failed:   agents.filter(a => a.status === "failed").length,
    offline:  agents.filter(a => a.status === "offline" || a.status === "waiting").length,
  }), [agents]);

  const grouped = useMemo(() => {
    if (activeTier !== "ALL") return [{ tier: activeTier, items: filtered }];
    return FLEET_TIERS.map(t => ({
      tier: t.id,
      items: agents.filter(a => a.tier === t.id),
    }));
  }, [filtered, agents, activeTier]);

  const now = new Date();
  const nowFrac = (now.getUTCHours() + now.getUTCMinutes() / 60) / 24;

  return (
    <div className="fleet-page" style={{
      minHeight: "100vh",
      background:
        "var(--vignette), var(--scanlines), var(--bg-1)",
      backgroundAttachment: "fixed",
    }}>
      <style>{`
        .fleet-page .console { display: flex; min-height: 100vh; }
        .fleet-page .fleet-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
        .fleet-page .fleet-content {
          flex: 1;
          padding: 22px 24px 24px;
          display: grid;
          grid-template-columns: 1fr 360px;
          gap: 18px;
          align-items: start;
        }
        .fleet-page .fleet-roster {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 14px;
        }
        @media (max-width: 1200px) {
          .fleet-page .fleet-content { grid-template-columns: 1fr; }
        }
        @media (max-width: 720px) {
          .fleet-page .fleet-roster { grid-template-columns: 1fr; }
          .fleet-page aside { display: none; }
        }
        .fleet-page .fleet-tier-header {
          grid-column: 1 / -1;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 4px 0 0;
        }
        .fleet-page .fleet-tier-header .bar { flex: 1; height: 4px; }
        .fleet-page button { font-family: inherit; }
      `}</style>

      <div className="console">
        <FleetSidebar
          tiers={FLEET_TIERS}
          activeTier={activeTier}
          setActiveTier={setActiveTier}
          summary={summary}
        />
        <div className="fleet-main">
          <FleetHeader
            clock={clock}
            onSummon={() => setSummonOpen(true)}
            onBack={() => navigate("/")}
            agentCount={agents.length}
          />
          <div className="fleet-content">
            <div className="fleet-roster">
              {grouped.map(g => {
                const tierMeta = FLEET_TIERS.find(t => t.id === g.tier);
                if (!tierMeta) return null;
                return (
                  <div key={g.tier} style={{ display: "contents" }}>
                    <div className="fleet-tier-header">
                      <span className="t-callsign" style={{ color: `var(--tier-${g.tier})`, fontSize: 11 }}>
                        ▣ {tierMeta.label}
                      </span>
                      <span className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9 }}>{tierMeta.role.toUpperCase()}</span>
                      <span className="bar" style={{ background: `linear-gradient(90deg, var(--tier-${g.tier}), transparent)` }} />
                      <span className="t-callsign" style={{ color: "var(--fg-3)", fontSize: 9 }}>{g.items.length} AGENTS</span>
                    </div>
                    {g.items.map(a => (
                      <AgentCard
                        key={a.id}
                        agent={a}
                        selected={selected?.id === a.id}
                        onClick={() => setSelected(a)}
                      />
                    ))}
                  </div>
                );
              })}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "sticky", top: 70 }}>
              <LogFeed events={logs} />
              <ScheduleStrip events={SCHEDULE} nowFrac={nowFrac} />
              <div style={{ background: "var(--bg-3)", border: "2px solid var(--bg-0)", padding: "10px 12px", boxShadow: "var(--px-inset-up)" }}>
                <div className="t-callsign" style={{ color: "var(--fg-5)", marginBottom: 4 }}>TIP</div>
                <div style={{ font: "var(--t-body-pixel)", color: "var(--fg-3)", fontSize: 11 }}>
                  Press <span style={{ color: "var(--cyan)" }}>[ / ]</span> to summon · click any operator for the playbook.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <AgentDialog agent={selected} onClose={() => setSelected(null)} />
      <SummonPalette
        open={summonOpen}
        onClose={() => setSummonOpen(false)}
        onSubmit={() => setSummonOpen(false)}
      />
    </div>
  );
}
