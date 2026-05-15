/* Fleet Console — components.
   All inline styles use the global CSS vars from colors_and_type.css. */

const { useState, useEffect, useRef, useMemo } = React;

/* ------------ MeterBar ------------ */
function MeterBar({ value, max, color, label, right }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", font: "var(--t-callsign)", letterSpacing: "var(--tracking-loose)", textTransform: "uppercase" }}>
        <span style={{ color }}>{label}</span>
        <span className="t-callsign" style={{ color: "var(--fg-2)" }}>{right ?? `${value}/${max}`}</span>
      </div>
      <div style={{ height: 10, background: "var(--meter-bg)", border: "2px solid var(--bg-0)", marginTop: 3, padding: 1 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, boxShadow: "inset 0 -2px 0 rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.22)", transition: "width var(--dur-2) var(--ease-step)" }} />
      </div>
    </div>
  );
}

/* ------------ StatusLED ------------ */
function StatusLED({ status }) {
  const map = {
    online:   { c: "var(--ok)",     glow: "var(--ok-glow)",     pulse: true,  speed: "1s" },
    waiting:  { c: "var(--info)",   glow: "var(--accent-glow)", pulse: false },
    degraded: { c: "var(--warn)",   glow: "var(--warn-glow)",   pulse: false },
    failed:   { c: "var(--danger)", glow: "var(--danger-glow)", pulse: true,  speed: "0.55s" },
    offline:  { c: "var(--idle)",   glow: "transparent",        pulse: false, dim: true },
  }[status] || { c: "var(--idle)", glow: "transparent" };
  return (
    <span style={{
      display: "inline-block", width: 10, height: 10,
      background: map.c,
      boxShadow: `0 0 10px ${map.glow}`,
      border: map.dim ? "1px solid var(--fg-4)" : "none",
      animation: map.pulse ? `blink-led ${map.speed} steps(2,end) infinite` : "none",
    }} />
  );
}

/* ------------ Tier chip ------------ */
function TierChip({ tier, label }) {
  const colorVar = `var(--tier-${tier})`;
  const washMap = {
    ingest: "rgba(54,153,255,0.16)",
    enrich: "rgba(183,148,246,0.16)",
    quality: "rgba(94,234,212,0.16)",
    cloud: "rgba(255,168,0,0.16)",
    delivery: "rgba(244,114,182,0.16)",
  };
  return (
    <span style={{
      padding: "4px 7px",
      background: washMap[tier],
      color: colorVar,
      border: `2px solid ${colorVar}`,
      font: "var(--t-callsign)",
      letterSpacing: "var(--tracking-loose)",
      textTransform: "uppercase",
      fontSize: 10,
    }}>{label}</span>
  );
}

/* ------------ AgentCard ------------ */
function AgentCard({ agent, selected, onClick }) {
  const tierVar = `var(--tier-${agent.tier})`;
  const washMap = {
    ingest: "rgba(54,153,255,0.16)",
    enrich: "rgba(183,148,246,0.16)",
    quality: "rgba(94,234,212,0.16)",
    cloud: "rgba(255,168,0,0.16)",
    delivery: "rgba(244,114,182,0.16)",
  };
  const stateGlow = {
    failed: "var(--glow-dngr)",
    degraded: "var(--glow-warn)",
  }[agent.status];

  return (
    <div
      onClick={onClick}
      style={{
        cursor: "pointer",
        background: "var(--bg-3)",
        border: "2px solid var(--bg-0)",
        boxShadow: selected
          ? `var(--glow-blue), var(--px-shadow-2), var(--px-inset-up)`
          : (stateGlow ? `${stateGlow}, var(--px-shadow-2), var(--px-inset-up)` : "var(--px-shadow-2), var(--px-inset-up)"),
        position: "relative",
        transition: "transform var(--dur-1) var(--ease-out)",
      }}
      onMouseEnter={e => e.currentTarget.style.transform = "translateY(-2px)"}
      onMouseLeave={e => e.currentTarget.style.transform = "translateY(0)"}
    >
      {/* Tier strip */}
      <div style={{
        height: 4,
        background: `linear-gradient(90deg, ${tierVar}, ${washMap[agent.tier]})`,
      }} />
      {/* Status LED */}
      <div style={{ position: "absolute", top: 14, right: 12 }}><StatusLED status={agent.status} /></div>
      {/* Body */}
      <div style={{ padding: "12px", display: "flex", gap: 12 }}>
        <div style={{
          width: 56, height: 56,
          background: washMap[agent.tier],
          border: `2px solid ${tierVar}`,
          display: "grid", placeItems: "center",
          flexShrink: 0,
        }}>
          <Sprite agentId={agent.id} tier={agent.tier} size={48} breathe={agent.status === "online"} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="t-callsign" style={{ color: tierVar, fontSize: 10 }}>
            {agent.tier.toUpperCase()} · {agent.type.toUpperCase()}
          </div>
          <h3 style={{ color: "var(--fg-1)", margin: "2px 0 4px", font: "var(--t-h3)", fontSize: 13, wordBreak: "break-all" }}>
            {agent.id}
          </h3>
          <div style={{ font: "var(--t-body-pixel)", fontSize: 11, color: "var(--fg-3)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {agent.desc}
          </div>
        </div>
      </div>
      {/* Meters */}
      <div style={{ padding: "0 12px 10px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <MeterBar value={agent.hp} max={100} color="var(--hp-fill)" label="HP" right={`${agent.hp}%`} />
          <MeterBar value={agent.xp} max={agent.xpMax} color="var(--xp-fill)" label="XP" />
        </div>
      </div>
      {/* Stat strip */}
      <div style={{
        borderTop: "2px solid var(--bg-0)",
        background: "var(--bg-2)",
        display: "grid",
        gridTemplateColumns: "1fr 1fr 1fr",
        font: "var(--t-callsign)",
        letterSpacing: "var(--tracking-loose)",
      }}>
        <div style={{ padding: "7px 9px", borderRight: "2px solid var(--bg-0)" }}>
          <div style={{ color: "var(--fg-4)", fontSize: 9 }}>LAST</div>
          <div style={{ color: "var(--fg-1)", font: "var(--t-subtitle)", fontSize: 11, marginTop: 2 }}>{agent.last}</div>
        </div>
        <div style={{ padding: "7px 9px", borderRight: "2px solid var(--bg-0)" }}>
          <div style={{ color: "var(--fg-4)", fontSize: 9 }}>NEXT</div>
          <div style={{ color: "var(--cyan)", font: "var(--t-subtitle)", fontSize: 11, marginTop: 2 }}>{agent.next}</div>
        </div>
        <div style={{ padding: "7px 9px" }}>
          <div style={{ color: "var(--fg-4)", fontSize: 9 }}>CYCLE</div>
          <div style={{ color: "var(--fg-1)", font: "var(--t-subtitle)", fontSize: 11, marginTop: 2 }}>{agent.avgCycle}</div>
        </div>
      </div>
    </div>
  );
}

/* ------------ Sidebar (tier nav) ------------ */
function Sidebar({ tiers, activeTier, setActiveTier, summary }) {
  return (
    <aside style={{
      width: 240, flex: "0 0 240px",
      background: "var(--bg-2)",
      borderRight: "2px solid var(--bg-0)",
      padding: "18px 14px",
      display: "flex", flexDirection: "column", gap: 18,
      height: "100vh", position: "sticky", top: 0,
      overflowY: "auto",
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 14, borderBottom: "2px solid var(--bg-0)" }}>
        <div style={{ width: 36, height: 36, background: "var(--bg-3)", border: "2px solid var(--bg-0)", display: "grid", placeItems: "center", boxShadow: "var(--px-inset-up)" }}>
          <svg width="24" height="24" viewBox="0 0 16 16" shapeRendering="crispEdges">
            <rect x="2" y="6" width="12" height="3" fill="#3699FF"/>
            <rect x="3" y="5" width="10" height="1" fill="#3699FF"/>
            <rect x="4" y="4" width="8" height="1" fill="#3699FF"/>
            <rect x="5" y="5" width="2" height="1" fill="#0b0d14"/>
            <rect x="9" y="5" width="2" height="1" fill="#0b0d14"/>
            <rect x="3" y="9" width="2" height="2" fill="#0b0d14"/>
            <rect x="11" y="9" width="2" height="2" fill="#0b0d14"/>
          </svg>
        </div>
        <div>
          <div style={{ font: "var(--t-subtitle)", fontSize: 11, color: "var(--fg-1)", lineHeight: 1.2 }}>CARPAPI</div>
          <div className="t-callsign" style={{ color: "var(--accent)", fontSize: 9 }}>FLEET · v0.1</div>
        </div>
      </div>

      {/* Summary HUD */}
      <div style={{ background: "var(--bg-3)", border: "2px solid var(--bg-0)", padding: 10, boxShadow: "var(--px-inset-up)" }}>
        <div className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9, marginBottom: 6 }}>FLEET STATUS</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, font: "var(--t-callsign)" }}>
          <div><div style={{ color: "var(--ok)", font: "var(--t-stat-sm)", fontSize: 16 }}>{summary.online}</div><div style={{ color: "var(--fg-4)", fontSize: 9 }}>ONLINE</div></div>
          <div><div style={{ color: "var(--warn)", font: "var(--t-stat-sm)", fontSize: 16 }}>{summary.degraded}</div><div style={{ color: "var(--fg-4)", fontSize: 9 }}>DEGRADE</div></div>
          <div><div style={{ color: "var(--danger)", font: "var(--t-stat-sm)", fontSize: 16 }}>{summary.failed}</div><div style={{ color: "var(--fg-4)", fontSize: 9 }}>FAILED</div></div>
          <div><div style={{ color: "var(--idle)", font: "var(--t-stat-sm)", fontSize: 16 }}>{summary.offline}</div><div style={{ color: "var(--fg-4)", fontSize: 9 }}>DORMANT</div></div>
        </div>
      </div>

      {/* Tier nav */}
      <div>
        <div className="t-callsign" style={{ color: "var(--fg-5)", fontSize: 9, marginBottom: 8, padding: "0 4px" }}>FILTER · TIER</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <TierRow id="ALL" label="ALL TIERS" count={14} color="var(--accent)" active={activeTier==="ALL"} onClick={() => setActiveTier("ALL")} />
          {tiers.map(t => (
            <TierRow key={t.id} id={t.id} label={t.label} count={t.count} color={t.color} active={activeTier===t.id} onClick={() => setActiveTier(t.id)} />
          ))}
        </div>
      </div>
    </aside>
  );
}

function TierRow({ id, label, count, color, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "8px 10px",
      background: active ? "var(--bg-3)" : "transparent",
      border: "2px solid " + (active ? color : "transparent"),
      color: active ? color : "var(--fg-3)",
      font: "var(--t-callsign)",
      letterSpacing: "var(--tracking-loose)",
      fontSize: 11,
      textTransform: "uppercase",
      cursor: "pointer",
      width: "100%",
      textAlign: "left",
      boxShadow: active ? "var(--px-inset-up)" : "none",
    }}>
      <span style={{ width: 8, height: 8, background: color, flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{label}</span>
      <span style={{ color: active ? color : "var(--fg-4)", fontSize: 10 }}>{count}</span>
    </button>
  );
}

/* ------------ Top header / HUD ------------ */
function Header({ clock, onSummon }) {
  return (
    <header style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "14px 22px",
      background: "var(--bg-2)",
      borderBottom: "2px solid var(--bg-0)",
      position: "sticky", top: 0, zIndex: 10,
    }}>
      <div>
        <div className="t-callsign" style={{ color: "var(--accent)", fontSize: 10 }}>MISSION CONTROL · ROSTER</div>
        <h1 style={{ color: "var(--fg-1)", marginTop: 4, font: "var(--t-h1)", fontSize: 18 }}>14 OPERATORS DEPLOYED</h1>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <HudStat label="UTC" value={clock} color="var(--cyan)" />
        <HudStat label="LISTINGS" value="12,847" color="var(--fg-1)" />
        <HudStat label="BUDGET" value="$92/100" color="var(--warn)" />
        <button onClick={onSummon} className="px-btn primary">► SUMMON</button>
      </div>
    </header>
  );
}

function HudStat({ label, value, color }) {
  return (
    <div style={{ textAlign: "right", paddingRight: 14, borderRight: "2px solid var(--bg-0)" }}>
      <div className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9 }}>{label}</div>
      <div style={{ color, font: "var(--t-subtitle)", fontSize: 13, marginTop: 2 }}>{value}</div>
    </div>
  );
}

/* ------------ Activity Log feed ------------ */
function LogFeed({ events }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [events.length]);
  const toneColor = { ok: "var(--ok)", info: "var(--cyan)", warn: "var(--warn)", err: "var(--danger)" };
  return (
    <div style={{
      background: "var(--bg-0)",
      border: "2px solid var(--bg-0)",
      boxShadow: "var(--px-inset-up)",
      height: 280,
      display: "flex",
      flexDirection: "column",
    }}>
      <div style={{ padding: "8px 12px", background: "var(--bg-2)", borderBottom: "2px solid var(--bg-0)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="t-callsign" style={{ color: "var(--ok)" }}>▣ LIVE ACTIVITY FEED</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <StatusLED status="online" />
          <span className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9 }}>TAILING</span>
        </div>
      </div>
      <div ref={ref} style={{ flex: 1, overflowY: "auto", padding: "10px 12px", font: "var(--t-body)" }}>
        {events.map((e, i) => (
          <div key={i} style={{ marginBottom: 2, display: "flex", gap: 8 }}>
            <span style={{ color: "var(--fg-5)" }}>[{e.time}]</span>
            <span style={{ color: "var(--accent-hi)", width: 168, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.agent}</span>
            <span style={{ color: toneColor[e.tone] || "var(--fg-2)" }}>{e.text}</span>
          </div>
        ))}
        <div style={{ color: "var(--ok)" }}>&gt; <span style={{ animation: "blink-led 0.8s steps(2,end) infinite" }}>_</span></div>
      </div>
    </div>
  );
}

/* ------------ Schedule strip ------------ */
function ScheduleStrip({ events, nowFrac }) {
  return (
    <div style={{ background: "var(--bg-2)", border: "2px solid var(--bg-0)", padding: "12px 14px", boxShadow: "var(--px-inset-up)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div className="t-callsign" style={{ color: "var(--fg-3)" }}>DAILY SCHEDULE · UTC</div>
        <div className="t-callsign" style={{ color: "var(--cyan)", fontSize: 9 }}>NOW {Math.round(nowFrac * 24).toString().padStart(2,'0')}:00</div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", font: "var(--t-callsign)", color: "var(--fg-4)", fontSize: 9, marginBottom: 4 }}>
        {[0,3,6,9,12,15,18,21,24].map(h => <span key={h}>{h.toString().padStart(2,'0')}</span>)}
      </div>
      <div style={{ position: "relative", height: 14, background: "var(--bg-0)", border: "1px solid var(--bg-4)" }}>
        <div style={{ position: "absolute", left: `${nowFrac * 100}%`, top: -4, bottom: -4, width: 2, background: "var(--cyan)", boxShadow: "0 0 10px var(--cyan-glow)" }} />
        {events.map((e, i) => (
          <div
            key={i}
            title={`${e.hour.toString().padStart(2,'0')}:00 ${e.id}`}
            style={{
              position: "absolute",
              left: `${(e.hour / 24) * 100}%`,
              top: 0, bottom: 0, width: 6,
              background: `var(--tier-${e.tier})`,
            }}
          />
        ))}
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 10, font: "var(--t-callsign)", fontSize: 10 }}>
        {events.map((e, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, background: `var(--tier-${e.tier})` }} />
            <span style={{ color: `var(--tier-${e.tier})` }}>{e.hour.toString().padStart(2,'0')}:00</span>
            <span style={{ color: "var(--fg-3)" }}>{e.id}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------ Dialog (agent detail modal) ------------ */
function AgentDialog({ agent, onClose }) {
  if (!agent) return null;
  const tierVar = `var(--tier-${agent.tier})`;
  const washMap = {
    ingest: "rgba(54,153,255,0.16)",
    enrich: "rgba(183,148,246,0.16)",
    quality: "rgba(94,234,212,0.16)",
    cloud: "rgba(255,168,0,0.16)",
    delivery: "rgba(244,114,182,0.16)",
  };
  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0,
      background: "rgba(11,13,20,0.78)",
      backdropFilter: "blur(4px)",
      display: "grid", placeItems: "center",
      zIndex: 100,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 560, maxWidth: "92vw",
        background: "var(--bg-3)",
        border: `2px solid ${tierVar}`,
        boxShadow: `0 0 0 2px var(--bg-0), 0 0 30px ${tierVar.replace('var(--', '').replace(')', '') === 'tier-ingest' ? 'var(--accent-glow)' : 'rgba(0,0,0,0)'}, var(--px-shadow-3)`,
      }}>
        {/* Tier strip */}
        <div style={{ height: 6, background: tierVar }} />
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", background: "var(--bg-2)", borderBottom: "2px solid var(--bg-0)" }}>
          <div style={{ width: 64, height: 64, background: washMap[agent.tier], border: `2px solid ${tierVar}`, display: "grid", placeItems: "center", flexShrink: 0 }}>
            <Sprite agentId={agent.id} tier={agent.tier} size={56} breathe={agent.status === "online"} />
          </div>
          <div style={{ flex: 1 }}>
            <div className="t-callsign" style={{ color: tierVar }}>{agent.tier.toUpperCase()} · {agent.type.toUpperCase()} · {agent.cadence.toUpperCase()}</div>
            <div style={{ color: "var(--fg-1)", font: "var(--t-h2)", marginTop: 4, wordBreak: "break-all" }}>{agent.id}</div>
          </div>
          <button onClick={onClose} className="px-btn" style={{ fontSize: 10 }}>[ESC] CLOSE</button>
        </div>
        {/* Body */}
        <div style={{ padding: "18px", display: "flex", flexDirection: "column", gap: 14 }}>
          <p style={{ font: "var(--t-body-pixel)", color: "var(--fg-2)", fontSize: 13, lineHeight: 1.5 }}>{agent.desc}</p>

          {/* Stats grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            <Stat label="STATUS" value={agent.status} valueColor={
              agent.status === "online" ? "var(--ok)" :
              agent.status === "failed" ? "var(--danger)" :
              agent.status === "degraded" ? "var(--warn)" :
              agent.status === "waiting" ? "var(--info)" : "var(--idle)"
            } />
            <Stat label="LAST RUN" value={agent.last} />
            <Stat label="NEXT" value={agent.next} valueColor="var(--cyan)" />
            <Stat label="CYCLE" value={agent.avgCycle} />
          </div>

          {/* Meters */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <MeterBar value={agent.hp} max={100} color="var(--hp-fill)" label="HP · UPTIME" right={`${agent.hp}%`} />
            <MeterBar value={agent.xp} max={agent.xpMax} color="var(--xp-fill)" label="XP · TODAY" />
          </div>

          {/* Trigger phrases */}
          <div>
            <div className="t-callsign" style={{ color: "var(--fg-5)", marginBottom: 6 }}>TRIGGER PHRASES</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {agent.triggers.map((t, i) => (
                <span key={i} style={{ padding: "5px 8px", background: "var(--bg-0)", border: "2px solid var(--bg-4)", font: "var(--t-mono)", fontSize: 11, color: "var(--cyan)" }}>{t}</span>
              ))}
            </div>
          </div>
        </div>
        {/* Actions */}
        <div style={{ padding: "12px 16px", borderTop: "2px solid var(--bg-0)", background: "var(--bg-2)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="t-callsign" style={{ color: "var(--fg-4)" }}>READS: .claude/agents/{agent.id}.md</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="px-btn">▣ LOGS</button>
            <button className="px-btn">⟲ RERUN</button>
            <button className="px-btn primary">► SUMMON</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, valueColor }) {
  return (
    <div style={{ background: "var(--bg-2)", border: "2px solid var(--bg-0)", padding: "8px 10px", boxShadow: "var(--px-inset-up)" }}>
      <div className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9 }}>{label}</div>
      <div style={{ color: valueColor || "var(--fg-1)", font: "var(--t-subtitle)", fontSize: 11, marginTop: 3, textTransform: "uppercase" }}>{value}</div>
    </div>
  );
}

/* ------------ Summon command palette ------------ */
function SummonPalette({ open, onClose, onSubmit }) {
  const [value, setValue] = useState("");
  const inputRef = useRef(null);
  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);
  if (!open) return null;
  const suggestions = [
    { phrase: "rescrape performance-ford", agent: "scraper-dispatcher", tier: "ingest" },
    { phrase: "deploy",                    agent: "carpapi-deployer",   tier: "cloud" },
    { phrase: "audit data",                agent: "data-quality-auditor", tier: "quality" },
    { phrase: "why is CI red?",            agent: "ci-cd-doctor",       tier: "delivery" },
    { phrase: "find Toyota dealers in NJ", agent: "dealer-prospector",  tier: "ingest" },
  ];
  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0,
      background: "rgba(11,13,20,0.78)",
      backdropFilter: "blur(4px)",
      display: "flex", justifyContent: "center", paddingTop: "18vh",
      zIndex: 200,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: 520, maxWidth: "92vw", height: "fit-content",
        background: "var(--bg-3)",
        border: "2px solid var(--accent)",
        boxShadow: "0 0 0 2px var(--bg-0), 0 0 36px var(--accent-glow), var(--px-shadow-3)",
      }}>
        <div style={{ padding: "10px 14px", background: "var(--bg-2)", borderBottom: "2px solid var(--bg-0)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="t-callsign" style={{ color: "var(--accent)" }}>▣ SUMMON AGENT</div>
          <div className="t-callsign" style={{ color: "var(--fg-4)", fontSize: 9 }}>[ESC]</div>
        </div>
        <div style={{ padding: 14, display: "flex", gap: 8 }}>
          <span style={{ color: "var(--cyan)", font: "var(--t-body)", paddingTop: 6 }}>&gt;</span>
          <input
            ref={inputRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { onSubmit(value); setValue(""); } }}
            placeholder="rescrape performance-ford"
            style={{
              flex: 1, background: "transparent", border: "none", outline: "none",
              font: "var(--t-body)", color: "var(--fg-1)", fontSize: 18,
              caretColor: "var(--cyan)",
            }}
          />
        </div>
        <div style={{ padding: "0 14px 14px" }}>
          <div className="t-callsign" style={{ color: "var(--fg-5)", marginBottom: 8 }}>SUGGESTED</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => { setValue(s.phrase); onSubmit(s.phrase); }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 10px",
                  background: "var(--bg-2)",
                  border: "2px solid var(--bg-0)",
                  color: "var(--fg-2)",
                  font: "var(--t-body-pixel)", fontSize: 12,
                  textAlign: "left", cursor: "pointer", width: "100%",
                  boxShadow: "var(--px-inset-up)",
                }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--bg-4)"}
                onMouseLeave={e => e.currentTarget.style.background = "var(--bg-2)"}
              >
                <span style={{ width: 8, height: 8, background: `var(--tier-${s.tier})` }} />
                <span style={{ flex: 1, color: "var(--cyan)" }}>"{s.phrase}"</span>
                <span className="t-callsign" style={{ color: `var(--tier-${s.tier})`, fontSize: 9 }}>→ {s.agent}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  AgentCard, Sidebar, Header, LogFeed, ScheduleStrip, AgentDialog,
  MeterBar, StatusLED, TierChip, SummonPalette,
});
