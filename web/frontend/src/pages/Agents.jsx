/**
 * /agents — live autonomous-fleet dashboard.
 *
 * Replaces the previous pixel-art "FleetConsole" mock with a real
 * data-driven view. Hits `GET /api/agents/` (see views_agents.py) on
 * mount + every 30 s; renders four KPI cards on top, then a sortable
 * roster table, then a recent-events feed of `done` / `handler_raised`
 * lines pulled from each deployed Lambda's CloudWatch log group.
 *
 * Visual language matches the rest of the SPA chrome (white cards,
 * 16px corners, the same "d4-pill" + tabular-nums conventions used
 * on /dealers + /listings). Inspired by demo4 dashboards' KPI strip
 * + roster + activity pattern, but re-implemented in plain inline
 * styles to avoid pulling in shadcn/Tailwind.
 *
 * Auth: public — the agents fleet roster is non-sensitive. (Lambda
 * configs and ARNs are stable values.) If we ever expose secret env
 * vars in the response, this needs IsAuthenticated.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { getAgents } from "../api.js";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";

// Two cadences:
//   - SLOW: normal dashboard heartbeat (30 s).
//   - FAST: while at least one agent is in `running` state (the user
//     just clicked ▶ Run and we're waiting for the dispatcher Lambda
//     to fire + publish a new state file).
// The fast-poll auto-times-out at RUN_TIMEOUT_MS — past that we
// assume the dispatcher / agent silently failed and reset the row.
const POLL_MS = 30_000;
const POLL_MS_FAST = 1_500;
const RUN_TIMEOUT_MS = 60_000;

// ── Visual tokens ────────────────────────────────────────────────────
const card = {
  background: "#fff",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 16,
  padding: "18px 20px",
};

const STATUS_PILL = {
  online:       { bg: "rgba(16,185,129,0.10)", fg: "#047857", label: "ONLINE",    dot: "#10b981" },
  idle:         { bg: "rgba(100,116,139,0.10)", fg: "#475569", label: "IDLE",      dot: "#94a3b8" },
  degraded:     { bg: "rgba(234,179,8,0.12)",   fg: "#854d0e", label: "DEGRADED", dot: "#eab308" },
  failed:       { bg: "rgba(220,38,38,0.10)",  fg: "#b91c1c", label: "FAILED",    dot: "#ef4444" },
  not_deployed: { bg: "rgba(0,0,0,0.04)",      fg: "#6b7280", label: "NOT DEPLOYED", dot: "#cbd5e1" },
};

const TIER_BADGE = {
  ingest:   { bg: "#eef2ff", fg: "#3730a3", label: "INGEST" },
  enrich:   { bg: "#ecfdf5", fg: "#065f46", label: "ENRICH" },
  quality:  { bg: "#fefce8", fg: "#854d0e", label: "QUALITY" },
  cloud:    { bg: "#eff6ff", fg: "#1d4ed8", label: "CLOUD-OPS" },
  delivery: { bg: "#fdf2f8", fg: "#9d174d", label: "DELIVERY" },
};

// ── Helpers ──────────────────────────────────────────────────────────
function fmtRelative(ts_ms) {
  if (!ts_ms) return "—";
  const sec = Math.max(0, Math.floor((Date.now() - ts_ms) / 1000));
  if (sec < 60)        return `${sec}s ago`;
  if (sec < 3600)      return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400)     return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function fmtCron(expr) {
  if (!expr) return "—";
  return expr.replace(/^cron\((.*)\)$/, "$1").replace(/\s+/g, " ").trim();
}

// ── Top-level page ───────────────────────────────────────────────────
export default function Agents() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tierFilter, setTierFilter] = useState("ALL");
  const [selectedSlug, setSelectedSlug] = useState(null);
  // `running` is the set of slugs awaiting their next state-file
  // publish. Shape: `{ slug: { queued_at_ms, started_at_ms } }`.
  // The fast-poll watches each running slug's `last_event.ts_ms`
  // — when it exceeds queued_at_ms, the run is done and the slug
  // is removed from this map.
  const [running, setRunning] = useState({});
  const [toast, setToast] = useState(null);

  const refreshRef = useRef(null);

  const refresh = async (opts = {}) => {
    const { initial = false, silent = false } = opts;
    if (initial) setLoading(true);
    else if (!silent) setRefreshing(true);
    try {
      const d = await getAgents();
      setData(d);
      setError(null);
      // Resolve any running slugs whose state file is now fresher
      // than queued_at_ms. (Hoisted out of the closure so the toast
      // text can name the agent + elapsed wall-clock seconds.)
      setRunning((prev) => {
        if (!Object.keys(prev).length) return prev;
        const next = { ...prev };
        for (const a of d.agents || []) {
          const r = next[a.slug];
          if (!r) continue;
          const ts = a.last_event?.ts_ms;
          if (ts && ts >= r.queued_at_ms) {
            const wall = Math.max(1, Math.round((Date.now() - r.started_at_ms) / 1000));
            setToast({
              kind: a.last_event.event === "handler_raised" ? "err" : "ok",
              msg: a.last_event.event === "handler_raised"
                ? `${a.slug} raised after ${wall}s`
                : `${a.slug} ran in ${wall}s`,
            });
            delete next[a.slug];
          }
        }
        // Timeout sweep — anything older than RUN_TIMEOUT_MS gets
        // dropped with a stale-state warning so the row doesn't
        // spin forever.
        const now = Date.now();
        for (const [slug, r] of Object.entries(next)) {
          if (now - r.started_at_ms > RUN_TIMEOUT_MS) {
            setToast({
              kind: "warn",
              msg: `${slug} didn't publish a fresh state within ${
                RUN_TIMEOUT_MS / 1000}s — check Logs.`,
            });
            delete next[slug];
          }
        }
        return next;
      });
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };
  refreshRef.current = refresh;

  // Polling cadence flips between FAST and SLOW depending on whether
  // anything is in the `running` map. Effect re-runs whenever the
  // set of running slugs changes — when it becomes empty, the
  // interval slows back down.
  useEffect(() => {
    refresh({ initial: true });
  }, []);

  useEffect(() => {
    const hasRunning = Object.keys(running).length > 0;
    const interval = hasRunning ? POLL_MS_FAST : POLL_MS;
    const t = setInterval(() => refreshRef.current({ silent: hasRunning }), interval);
    return () => clearInterval(t);
  }, [running]);

  // Auto-dismiss the run-result toast after 5 s so a successful run
  // doesn't permanently cover the bottom-right of the dashboard.
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5_000);
    return () => clearTimeout(t);
  }, [toast]);

  // Public hook used by the Run button below.
  const markRunning = (slug, queuedAtMs) => {
    setRunning((prev) => ({
      ...prev,
      [slug]: { queued_at_ms: queuedAtMs, started_at_ms: Date.now() },
    }));
  };

  const agents = data?.agents || [];
  const summary = data?.summary || {};
  const filtered = useMemo(
    () => tierFilter === "ALL" ? agents : agents.filter(a => a.tier === tierFilter),
    [agents, tierFilter],
  );
  const selected = useMemo(
    () => agents.find(a => a.slug === selectedSlug) || null,
    [agents, selectedSlug],
  );

  const successRate = summary.total
    ? Math.round(((summary.total - (summary.failed || 0) - (summary.degraded || 0)) / summary.total) * 100)
    : 100;

  return (
    <div className="d4-chat" data-theme="light" style={{ background: "#f7f8fa" }}>
      <PublicTopBar />

      {/* .d4-chat-scroller gives this <main> `flex: 1 1 auto; overflow-y:
          auto`, which is what makes the page actually scroll inside the
          fixed-viewport `.d4-chat` shell. Without this class the table
          overflows but the user can't reach it. */}
      <main
        className="d4-chat-scroller"
        style={{ padding: "24px 24px 48px" }}
      >
        <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        <header style={{
          display: "flex", justifyContent: "space-between", alignItems: "flex-end",
          gap: 12, flexWrap: "wrap", marginBottom: 22,
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: "#111" }}>
              Agent fleet
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 14, color: "#666" }}>
              Live status of the 14 autonomous agents that run CarPapi day to day.
              {data?.as_of_utc && (
                <> · as of <code style={{ fontSize: 12 }}>{data.as_of_utc}</code></>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={() => refresh(false)}
            disabled={refreshing}
            style={{
              padding: "8px 14px", borderRadius: 10,
              border: "1px solid rgba(0,0,0,0.12)", background: "#fff",
              color: "#111", fontSize: 13, fontWeight: 600,
              cursor: refreshing ? "default" : "pointer",
              opacity: refreshing ? 0.6 : 1,
            }}
          >
            <i className={`bi bi-arrow-clockwise ${refreshing ? "spin" : ""} me-1`} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </header>

        {error && (
          <div style={{
            padding: 14, borderRadius: 12, marginBottom: 16,
            background: "rgba(220,38,38,0.08)", color: "#b91c1c", fontSize: 14,
          }}>
            Couldn't load fleet status: {error}
          </div>
        )}

        {loading && !data && (
          <div style={{ padding: 40, textAlign: "center", color: "#666" }}>Loading…</div>
        )}

        {data && (
          <>
            <KpiStrip summary={summary} successRate={successRate} />
            <TierFilter active={tierFilter} onChange={setTierFilter} />
            <RosterTable
              agents={filtered}
              onSelect={setSelectedSlug}
              onOpenLogs={setSelectedSlug}
              running={running}
              onRun={(agent) => {
                // Optimistic: mark the row as "running…" instantly
                // (Date.now() is a sufficient queued_at_ms guess
                // until the backend response replaces it).
                const optimisticTs = Date.now();
                markRunning(agent.slug, optimisticTs);
                runAgentManually(agent, {
                  onQueued: (queuedAtMs) => {
                    // Replace with the authoritative ms from the
                    // backend so we don't false-positive-resolve on
                    // a clock skew.
                    markRunning(agent.slug, queuedAtMs ?? optimisticTs);
                  },
                  onError: (msg) => {
                    // Drop the row out of "running" and show an
                    // error toast.
                    setRunning((prev) => {
                      const next = { ...prev };
                      delete next[agent.slug];
                      return next;
                    });
                    setToast({
                      kind: "err",
                      msg: `Couldn't queue ${agent.slug}: ${msg}`,
                    });
                  },
                });
              }}
            />
            <ActivityFeed agents={agents} />
          </>
        )}
        </div>
      </main>

      {selected && (
        <AgentDrawer agent={selected} onClose={() => setSelectedSlug(null)} />
      )}

      <PublicFooter />

      {/* Toast — surfaces when a Run completes (or times out). */}
      {toast && (
        <div
          role="status"
          onClick={() => setToast(null)}
          style={{
            position: "fixed", bottom: 24, right: 24,
            padding: "12px 16px", borderRadius: 12,
            background:
              toast.kind === "ok"   ? "rgba(16,185,129,0.95)"
            : toast.kind === "err"  ? "rgba(220,38,38,0.95)"
            : /* warn */              "rgba(234,179,8,0.95)",
            color: "#fff",
            fontSize: 14, fontWeight: 600,
            boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
            cursor: "pointer",
            zIndex: 200,
            maxWidth: 360,
            animation: "carpapi-toast-in 0.2s ease",
          }}
        >
          {toast.msg}
        </div>
      )}

      {/* Animations for the refresh-spin icon, the row "running" pill,
          and the toast slide-in. */}
      <style>{`
        @keyframes carpapi-spin { to { transform: rotate(360deg); } }
        .spin { display: inline-block; animation: carpapi-spin 1s linear infinite; }
        @keyframes carpapi-pulse {
          0%, 100% { transform: scale(1);   opacity: 1; }
          50%      { transform: scale(1.6); opacity: 0.5; }
        }
        @keyframes carpapi-toast-in {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// Auto-dismiss the toast after 5 seconds (declared at module scope so
// it doesn't recreate per-render). Wrapped in a small effect-hook
// component would be cleaner, but a one-line tail in setToast() above
// would also work; opting for the smaller patch.

// ── KPI strip — four cards at the top, demo4-style ───────────────────
function KpiStrip({ summary, successRate }) {
  const items = [
    {
      label: "Agents online",
      value: `${summary.online || 0} / ${summary.total || 0}`,
      sub: `${summary.idle || 0} idle · ${summary.not_deployed || 0} unprovisioned`,
      tone: summary.online >= 1 ? "green" : "neutral",
    },
    {
      label: "Invocations (24h)",
      value: (summary.invocations_24h || 0).toLocaleString(),
      sub: `${summary.errors_24h || 0} errors`,
      tone: (summary.errors_24h || 0) > 0 ? "red" : "neutral",
    },
    {
      label: "Success rate",
      value: `${successRate}%`,
      sub: `${summary.degraded || 0} degraded · ${summary.failed || 0} failed`,
      tone: successRate === 100 ? "green" : successRate >= 80 ? "amber" : "red",
    },
    {
      label: "Next fire",
      value: "09:00 UTC",
      sub: "aws-cost-sentinel",
      tone: "neutral",
    },
  ];
  const toneBar = {
    green:   "#10b981",
    amber:   "#eab308",
    red:     "#ef4444",
    neutral: "#94a3b8",
  };
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
      gap: 14, marginBottom: 18,
    }}>
      {items.map((it, i) => (
        <motion.div
          key={it.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: i * 0.05 }}
          style={{ ...card, position: "relative", overflow: "hidden" }}
        >
          <div style={{
            position: "absolute", left: 0, top: 0, bottom: 0, width: 4,
            background: toneBar[it.tone],
          }} />
          <div style={{
            fontSize: 11, color: "#666", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            {it.label}
          </div>
          <div style={{
            fontSize: 28, fontWeight: 800, color: "#111", marginTop: 4,
            fontVariantNumeric: "tabular-nums",
          }}>
            {it.value}
          </div>
          <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>{it.sub}</div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Tier filter chips ────────────────────────────────────────────────
function TierFilter({ active, onChange }) {
  const tiers = ["ALL", "ingest", "enrich", "quality", "cloud", "delivery"];
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "0 0 14px" }}>
      {tiers.map((t) => {
        const tone = t !== "ALL" ? TIER_BADGE[t] : { bg: "#111", fg: "#fff", label: "ALL" };
        const on = active === t;
        return (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            style={{
              padding: "6px 12px", borderRadius: 99,
              border: "1px solid rgba(0,0,0,0.10)",
              background: on ? (t === "ALL" ? "#111" : tone.bg) : "#fff",
              color: on ? (t === "ALL" ? "#fff" : tone.fg) : "#444",
              fontSize: 12, fontWeight: 600, cursor: "pointer",
              textTransform: "uppercase", letterSpacing: "0.05em",
              transition: "background 0.15s",
            }}
          >
            {tone.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Per-row action buttons ──────────────────────────────────────────
// All three live in the same column so the row's onClick (which opens
// the side drawer) is preserved. Each action stops propagation so a
// button click doesn't also fire onSelect.
const REGION = "us-east-1";
const GH_AGENTS_BASE =
  "https://github.com/ceylanbagci/carpapi/blob/main/.claude/agents";

function cloudwatchLogsUrl(slug) {
  // App Runner can't reach Lambda APIs from the Django view, but
  // CloudWatch Logs is reachable through the AWS console (browser
  // session, not server). The Lambda log group convention is
  // /aws/lambda/carpapi-<slug>. If the Lambda doesn't exist yet,
  // CloudWatch shows "Log group does not exist" rather than crashing.
  const group = encodeURIComponent(`/aws/lambda/carpapi-${slug}`)
    .replace(/%/g, "$25");
  return (
    `https://console.aws.amazon.com/cloudwatch/home?region=${REGION}` +
    `#logsV2:log-groups/log-group/${group}`
  );
}

function RowActions({ agent, onRun, onOpenLogs, isRunning = false }) {
  const deployed = agent.status !== "not_deployed";
  const stop = (e) => e.stopPropagation();
  const btn = {
    fontSize: 11,
    fontWeight: 600,
    padding: "5px 9px",
    borderRadius: 6,
    border: "1px solid rgba(0,0,0,0.12)",
    background: "#fff",
    color: "#111",
    cursor: "pointer",
    textDecoration: "none",
    whiteSpace: "nowrap",
  };
  const btnDisabled = {
    ...btn, color: "#aaa", cursor: "not-allowed", background: "#fafafa",
  };
  // While the agent is in flight, swap the Run button for a spinner
  // pill so the user can see the action is mid-air (and can't
  // accidentally double-fire it).
  const runCells = isRunning ? (
    <button
      type="button"
      disabled
      title={`Waiting for ${agent.slug} to publish a fresh state file…`}
      style={{
        ...btn, cursor: "wait",
        color: "#854d0e", background: "rgba(234,179,8,0.10)",
        borderColor: "rgba(234,179,8,0.40)",
      }}
    >
      <span className="spin" style={{ display: "inline-block", marginRight: 4 }}>↻</span>
      running…
    </button>
  ) : (
    <button
      type="button"
      title={deployed
        ? `Trigger one manual run of ${agent.slug} via the run-queue`
        : `${agent.slug} is not deployed yet — nothing to run.`}
      onClick={(e) => { stop(e); if (deployed) onRun(agent); }}
      disabled={!deployed}
      style={deployed ? btn : btnDisabled}
    >
      ▶ Run
    </button>
  );
  return (
    <div
      style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}
      onClick={stop}
    >
      {runCells}
      {/* Logs opens the in-app side drawer (same view as clicking the
          row) — shows Lambda config + schedule + 24h metrics + the
          most recent event JSON published by the agent runner.
          A modifier-click (cmd/ctrl) falls back to the external
          CloudWatch console for power users. */}
      <button
        type="button"
        title={`Show ${agent.slug} logs in side panel (cmd/ctrl-click for CloudWatch console)`}
        onClick={(e) => {
          stop(e);
          if (e.metaKey || e.ctrlKey) {
            window.open(cloudwatchLogsUrl(agent.slug), "_blank", "noopener");
          } else {
            onOpenLogs(agent.slug);
          }
        }}
        style={btn}
      >
        Logs
      </button>
      <a
        href={`${GH_AGENTS_BASE}/${agent.slug}.md`}
        target="_blank"
        rel="noreferrer"
        title={`Open the agent spec for ${agent.slug}`}
        onClick={stop}
        style={btn}
      >
        Spec
      </a>
    </div>
  );
}

/** POSTs the run-queue marker, tells the page to start fast-polling
 *  for the agent's next state-file publish. The page polls until
 *  last_event.ts_ms exceeds queued_at_ms (run complete) or 60 s pass
 *  (timeout). UX-wise this hides the underlying async chain.
 */
async function runAgentManually(agent, { onQueued, onError }) {
  try {
    const r = await fetch(
      (window.__CARPAPI_API_BASE__ || "https://api.carpappi.com/api") +
        `/agents/${encodeURIComponent(agent.slug)}/run/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      },
    );
    if (!r.ok) {
      const body = await r.text();
      throw new Error(`HTTP ${r.status}: ${body.slice(0, 200)}`);
    }
    const data = await r.json();
    onQueued(data.queued_at_ms, data.queue_key);
  } catch (e) {
    onError(String(e.message || e));
  }
}

// ── Roster table — one row per agent ─────────────────────────────────
function RosterTable({ agents, onSelect, onOpenLogs, onRun, running = {} }) {
  return (
    <div style={{ ...card, padding: 0, marginBottom: 18, overflow: "hidden" }}>
      <table style={{
        width: "100%", borderCollapse: "collapse",
        fontSize: 14, fontVariantNumeric: "tabular-nums",
      }}>
        <thead>
          <tr style={{ background: "#fafbfc", borderBottom: "1px solid rgba(0,0,0,0.08)" }}>
            <Th>Agent</Th>
            <Th>Tier</Th>
            <Th>Type</Th>
            <Th>Status</Th>
            <Th align="right">Invocations 24h</Th>
            <Th align="right">Errors</Th>
            <Th align="right">Avg ms</Th>
            <Th>Cadence</Th>
            <Th>Last event</Th>
            <Th align="right">Actions</Th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => {
            const st = STATUS_PILL[a.status] || STATUS_PILL.not_deployed;
            const tier = TIER_BADGE[a.tier] || { bg: "#eee", fg: "#444", label: a.tier };
            const lastEv = a.last_event;
            return (
              <tr
                key={a.slug}
                onClick={() => onSelect(a.slug)}
                style={{
                  borderTop: "1px solid rgba(0,0,0,0.05)",
                  cursor: "pointer",
                  background: "transparent",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = "#f7f8fa"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              >
                <Td>
                  <div style={{ fontWeight: 600, color: "#111" }}>{a.slug}</div>
                  <div style={{
                    fontSize: 12, color: "#888",
                    maxWidth: 320, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>{a.desc}</div>
                </Td>
                <Td>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: "3px 8px",
                    borderRadius: 6, background: tier.bg, color: tier.fg,
                    letterSpacing: "0.04em",
                  }}>{tier.label}</span>
                </Td>
                <Td>
                  <span style={{ fontSize: 12, color: "#444", textTransform: "uppercase" }}>
                    {a.type}
                  </span>
                </Td>
                <Td>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 6,
                    fontSize: 11, fontWeight: 700, padding: "3px 9px",
                    borderRadius: 99, background: st.bg, color: st.fg,
                  }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: 99, background: st.dot,
                      boxShadow: a.status === "online" ? `0 0 4px ${st.dot}` : "none",
                    }} />
                    {st.label}
                  </span>
                </Td>
                <Td align="right">{a.metrics_24h?.invocations ?? "—"}</Td>
                <Td align="right" style={{
                  color: (a.metrics_24h?.errors || 0) > 0 ? "#b91c1c" : "#444",
                  fontWeight: (a.metrics_24h?.errors || 0) > 0 ? 700 : 400,
                }}>{a.metrics_24h?.errors ?? "—"}</Td>
                <Td align="right">{a.metrics_24h?.duration_avg_ms ?? "—"}</Td>
                <Td style={{ color: "#555", fontSize: 12 }}>
                  {a.schedule
                    ? <span title={fmtCron(a.schedule.expression)}>{a.cadence}</span>
                    : a.cadence}
                </Td>
                <Td style={{ fontSize: 12, color: "#666" }}>
                  {running[a.slug] ? (
                    // Running pill (yellow dot + "running…") replaces
                    // the last-event cell while the agent is in flight.
                    // The fast-poll resolves this within ~5-10 s.
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: 6,
                      fontSize: 11, fontWeight: 700, padding: "3px 9px",
                      borderRadius: 99,
                      background: "rgba(234,179,8,0.12)", color: "#854d0e",
                    }}>
                      <span style={{
                        width: 7, height: 7, borderRadius: 99,
                        background: "#eab308",
                        animation: "carpapi-pulse 1.2s ease-in-out infinite",
                      }} />
                      running…
                    </span>
                  ) : lastEv ? (
                    <>
                      <span style={{
                        color: lastEv.event === "handler_raised" ? "#b91c1c" : "#047857",
                        fontWeight: 600,
                      }}>
                        {lastEv.event === "handler_raised" ? "✕" : "✓"}
                      </span>
                      {" "}
                      {fmtRelative(lastEv.ts_ms)}
                    </>
                  ) : "—"}
                </Td>
                <Td align="right">
                  <RowActions
                    agent={a}
                    onRun={onRun}
                    onOpenLogs={onOpenLogs}
                    isRunning={!!running[a.slug]}
                  />
                </Td>
              </tr>
            );
          })}
          {!agents.length && (
            <tr>
              <Td colSpan={10} style={{ padding: 36, textAlign: "center", color: "#888" }}>
                No agents match this filter.
              </Td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Th({ children, align = "left" }) {
  return (
    <th style={{
      padding: "12px 14px", textAlign: align,
      fontSize: 11, fontWeight: 700, color: "#666",
      textTransform: "uppercase", letterSpacing: "0.05em",
    }}>{children}</th>
  );
}
function Td({ children, align = "left", colSpan, style }) {
  return (
    <td colSpan={colSpan} style={{
      padding: "12px 14px", textAlign: align,
      verticalAlign: "middle", ...(style || {}),
    }}>{children}</td>
  );
}

// ── Activity feed ────────────────────────────────────────────────────
function ActivityFeed({ agents }) {
  // Pull every agent's last_event into one chronological list.
  const events = useMemo(() => {
    const evs = agents
      .filter(a => a.last_event && a.last_event.ts_ms)
      .map(a => ({
        slug: a.slug,
        ts_ms: a.last_event.ts_ms,
        event: a.last_event.event,
        elapsed_s: a.last_event.elapsed_s,
        err: a.last_event.err,
        tone: a.last_event.tone,
      }))
      .sort((a, b) => b.ts_ms - a.ts_ms)
      .slice(0, 20);
    return evs;
  }, [agents]);

  return (
    <div style={card}>
      <div style={{
        fontSize: 14, fontWeight: 700, color: "#111", marginBottom: 12,
      }}>
        Recent activity
      </div>
      {!events.length && (
        <div style={{ fontSize: 13, color: "#888" }}>
          No agent invocations recorded yet. The first will appear here within
          ~1 minute of any agent firing.
        </div>
      )}
      {events.map((e, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "8px 0",
          borderTop: i ? "1px solid rgba(0,0,0,0.05)" : "none",
          fontSize: 13,
        }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 22, height: 22, borderRadius: 6,
            background: e.event === "handler_raised" ? "rgba(220,38,38,0.10)" : "rgba(16,185,129,0.10)",
            color: e.event === "handler_raised" ? "#b91c1c" : "#047857",
            fontSize: 12, fontWeight: 700,
          }}>
            {e.event === "handler_raised" ? "✕" : "✓"}
          </span>
          <code style={{ fontWeight: 600, color: "#111", fontSize: 12 }}>{e.slug}</code>
          <span style={{ color: "#666", flex: 1 }}>
            {e.event === "handler_raised"
              ? <>raised <code style={{ fontSize: 12 }}>{e.err || "?"}</code></>
              : <>done in {e.elapsed_s ?? "?"}s{e.tone ? ` (${e.tone})` : ""}</>}
          </span>
          <span style={{ color: "#888", fontSize: 12 }}>{fmtRelative(e.ts_ms)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Drawer for the selected agent ────────────────────────────────────
function AgentDrawer({ agent, onClose }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.35)",
        display: "flex", justifyContent: "flex-end",
        zIndex: 100,
      }}
    >
      <motion.aside
        initial={{ x: 30, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.18 }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)", height: "100%",
          background: "#fff", padding: 28,
          overflowY: "auto",
          boxShadow: "-12px 0 30px rgba(0,0,0,0.10)",
        }}
      >
        <button
          type="button"
          onClick={onClose}
          style={{
            position: "absolute", top: 12, right: 14,
            background: "transparent", border: "none",
            fontSize: 22, cursor: "pointer", color: "#666",
          }}
          aria-label="Close"
        >×</button>

        <div style={{ marginBottom: 18 }}>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#111" }}>
            {agent.slug}
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "#555" }}>{agent.desc}</p>
        </div>

        <Section title="Status">
          <KV k="Tier" v={(TIER_BADGE[agent.tier] || {}).label || agent.tier} />
          <KV k="Type" v={agent.type} />
          <KV k="Cadence" v={agent.cadence} />
          <KV k="Deployed" v={agent.deployed ? "yes" : "no"} />
          <KV k="Current state" v={(STATUS_PILL[agent.status] || {}).label || agent.status} />
        </Section>

        {agent.lambda && (
          <Section title="Lambda function">
            <KV k="ARN" v={<code style={{ fontSize: 11 }}>{agent.lambda.arn}</code>} />
            <KV k="State" v={agent.lambda.state} />
            <KV k="Memory" v={`${agent.lambda.memory_mb} MB`} />
            <KV k="Timeout" v={`${agent.lambda.timeout_s} s`} />
            <KV k="Package" v={agent.lambda.package_type} />
            <KV k="Updated" v={agent.lambda.last_modified} />
          </Section>
        )}

        {agent.schedule && (
          <Section title="EventBridge schedule">
            <KV k="Name" v={agent.schedule.name} />
            <KV k="Expression" v={<code style={{ fontSize: 11 }}>{agent.schedule.expression}</code>} />
            <KV k="Timezone" v={agent.schedule.timezone} />
            <KV k="State" v={agent.schedule.state} />
          </Section>
        )}

        <Section title="Last 24 h metrics">
          <KV k="Invocations" v={agent.metrics_24h.invocations} />
          <KV k="Errors" v={agent.metrics_24h.errors} />
          <KV k="Avg duration" v={agent.metrics_24h.duration_avg_ms != null
            ? `${agent.metrics_24h.duration_avg_ms} ms` : "—"} />
        </Section>

        {agent.last_event && (
          <Section title="Most recent event (last 7 days)">
            <pre style={{
              fontSize: 11, lineHeight: 1.5,
              background: "#f7f8fa", padding: 12, borderRadius: 8,
              border: "1px solid rgba(0,0,0,0.06)",
              overflow: "auto",
            }}>
              {JSON.stringify(agent.last_event, null, 2)}
            </pre>
          </Section>
        )}
      </motion.aside>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: "#666",
        textTransform: "uppercase", letterSpacing: "0.05em",
        marginBottom: 8,
      }}>{title}</div>
      <div style={{
        background: "#fafbfc", border: "1px solid rgba(0,0,0,0.06)",
        borderRadius: 10, padding: "8px 12px",
      }}>{children}</div>
    </div>
  );
}
function KV({ k, v }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", gap: 12,
      padding: "5px 0", fontSize: 13,
      borderTop: "1px solid rgba(0,0,0,0.04)",
    }}>
      <span style={{ color: "#666" }}>{k}</span>
      <span style={{ color: "#111", textAlign: "right", maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis" }}>
        {v ?? "—"}
      </span>
    </div>
  );
}
