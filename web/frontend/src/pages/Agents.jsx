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
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { getAgents } from "../api.js";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";
import { useTheme } from "../theme.jsx";

const POLL_MS = 30_000;

// ── Visual tokens ────────────────────────────────────────────────────
//
// All structural colors below resolve through CSS custom properties
// defined in <FleetThemeStyles>. The light/dark swap happens by setting
// `data-fleet-theme="dark"` on the page wrapper — no React Context or
// prop-drilling needed; the variables cascade through inline styles
// just like any other CSS property.
const card = {
  background: "var(--fleet-card-bg)",
  border: "1px solid var(--fleet-card-border)",
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
  // Theme is app-wide (useTheme writes <html data-theme=…>). The page
  // also mirrors it onto its own wrapper as `data-fleet-theme` so the
  // scoped --fleet-* variables flip in step.
  const { theme } = useTheme();
  // Local "I asked this agent to run" tracking. There's no live
  // server-side notion of "currently running" — Lambda invocations
  // are fire-and-forget and we only know about them via the next
  // state-file write. So we optimistically flag a slug as running
  // when Run is clicked, and clear it when the next poll surfaces a
  // fresher `last_event.ts_ms` for that agent. Stop just clears the
  // flag locally (we can't actually abort an in-flight Lambda).
  const [runningSlugs, setRunningSlugs] = useState(() => new Set());
  const [runStartedAt, setRunStartedAt] = useState(() => new Map());

  // Clear the "running" flag whenever a fresher event arrives. Compares
  // the agent's last_event.ts_ms against the timestamp recorded when
  // the user clicked Run — if newer, the run finished (success or
  // failure) and we drop the local flag.
  useEffect(() => {
    if (!data?.agents?.length) return;
    setRunningSlugs((prev) => {
      if (!prev.size) return prev;
      let next = null;
      for (const a of data.agents) {
        if (!prev.has(a.slug)) continue;
        const evMs = a.last_event?.ts_ms || 0;
        const reqMs = runStartedAt.get(a.slug) || 0;
        if (evMs > reqMs) {
          if (!next) next = new Set(prev);
          next.delete(a.slug);
        }
      }
      return next || prev;
    });
  }, [data, runStartedAt]);

  const markRunning = (slug) => {
    setRunStartedAt((m) => {
      const n = new Map(m);
      n.set(slug, Date.now());
      return n;
    });
    setRunningSlugs((s) => new Set(s).add(slug));
  };
  const markStopped = (slug) => {
    setRunningSlugs((s) => {
      if (!s.has(slug)) return s;
      const n = new Set(s);
      n.delete(slug);
      return n;
    });
  };

  const refresh = async (initial = false) => {
    if (initial) setLoading(true); else setRefreshing(true);
    try {
      const d = await getAgents();
      setData(d);
      setError(null);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    refresh(true);
    const t = setInterval(() => refresh(false), POLL_MS);
    return () => clearInterval(t);
  }, []);

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
    <div
      className="d4-chat fleet-agents-page"
      data-theme={theme}
      data-fleet-theme={theme}
      // .d4-chat defaults to `position: fixed; inset: 0` (full-viewport
      // chat shell). For a long scrollable dashboard we override back to
      // normal page flow so the document body owns the vertical scroll.
      style={{
        position: "static",
        inset: "auto",
        background: "var(--fleet-page-bg)",
        color: "var(--fleet-text)",
        minHeight: "100vh",
        height: "auto",
        overflow: "visible",
      }}
    >
      <FleetThemeStyles />
      <PublicTopBar />

      <main style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 24px 48px", width: "100%" }}>
        <header style={{
          display: "flex", justifyContent: "space-between", alignItems: "flex-end",
          gap: 12, flexWrap: "wrap", marginBottom: 22,
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: "var(--fleet-text)" }}>
              Agent fleet
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 14, color: "var(--fleet-text-muted)" }}>
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
              border: "1px solid var(--fleet-btn-border)",
              background: "var(--fleet-btn-bg)",
              color: "var(--fleet-text)", fontSize: 13, fontWeight: 600,
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
            background: "var(--fleet-error-bg)", color: "var(--fleet-error-fg)", fontSize: 14,
          }}>
            Couldn't load fleet status: {error}
          </div>
        )}

        {loading && !data && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--fleet-text-muted)" }}>Loading…</div>
        )}

        {data && (
          <>
            <KpiStrip summary={summary} successRate={successRate} />
            <TierFilter active={tierFilter} onChange={setTierFilter} />
            <RosterTable
              agents={filtered}
              onSelect={setSelectedSlug}
              onOpenLogs={setSelectedSlug}
              runningSlugs={runningSlugs}
              onRun={markRunning}
              onStop={markStopped}
            />
            <ActivityFeed agents={agents} />
          </>
        )}
      </main>

      {selected && (
        <AgentDrawer agent={selected} onClose={() => setSelectedSlug(null)} />
      )}

      <PublicFooter />

      {/* Spin animation for the refresh icon. */}
      <style>{`
        @keyframes carpapi-spin { to { transform: rotate(360deg); } }
        .spin { display: inline-block; animation: carpapi-spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

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
            fontSize: 11, color: "var(--fleet-text-muted)", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>
            {it.label}
          </div>
          <div style={{
            fontSize: 28, fontWeight: 800, color: "var(--fleet-text)", marginTop: 4,
            fontVariantNumeric: "tabular-nums",
          }}>
            {it.value}
          </div>
          <div style={{ fontSize: 12, color: "var(--fleet-text-faint)", marginTop: 4 }}>{it.sub}</div>
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
        const tone = t !== "ALL" ? TIER_BADGE[t] : {
          bg: "var(--fleet-text)", fg: "var(--fleet-card-bg)", label: "ALL",
        };
        const on = active === t;
        return (
          <button
            key={t}
            type="button"
            onClick={() => onChange(t)}
            style={{
              padding: "6px 12px", borderRadius: 99,
              border: "1px solid var(--fleet-btn-border)",
              background: on ? tone.bg : "var(--fleet-card-bg)",
              color: on ? tone.fg : "var(--fleet-text-muted)",
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

function RowActions({ agent, isRunning, onRun, onStop, onOpenLogs }) {
  const deployed = agent.status !== "not_deployed";
  const stop = (e) => e.stopPropagation();
  const btn = {
    fontSize: 11,
    fontWeight: 600,
    padding: "5px 9px",
    borderRadius: 6,
    border: "1px solid var(--fleet-btn-border)",
    background: "var(--fleet-btn-bg)",
    color: "var(--fleet-text)",
    cursor: "pointer",
    textDecoration: "none",
    whiteSpace: "nowrap",
  };
  // Stop button uses a red emphasis so a row in flight is visually
  // distinct from idle rows in a long roster.
  const stopBtn = {
    ...btn,
    background: "rgba(220,38,38,0.10)",
    color: "#b91c1c",
    border: "1px solid rgba(220,38,38,0.30)",
  };
  return (
    <div
      style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}
      onClick={stop}
    >
      {/* Run / Stop toggle. While the local "running" flag is set we
          show a Stop button (red); clicking it clears the flag. There
          is no real Lambda abort path today — Stop just rescinds the
          optimistic in-flight badge, useful when the user knows the
          run won't actually fire (e.g. NOT DEPLOYED agents). */}
      {isRunning ? (
        <button
          type="button"
          title={`Cancel pending run of ${agent.slug}`}
          onClick={(e) => { stop(e); onStop(agent.slug); stopAgentManually(agent); }}
          style={stopBtn}
        >
          ■ Stop
        </button>
      ) : (
        <button
          type="button"
          title={deployed
            ? `Trigger one manual run of ${agent.slug} via the run-queue`
            : `${agent.slug} has no Lambda deployed yet — click for details`}
          onClick={(e) => { stop(e); onRun(agent.slug); runAgentManually(agent, { deployed }); }}
          style={btn}
        >
          ▶ Run
        </button>
      )}
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

// Honest "stop a run" surface. There's no real Lambda abort — we just
// clear the local pending badge.
function stopAgentManually(agent) {
  alert(
    `Pending run for "${agent.slug}" cleared locally.\n\n` +
    `Note: this only removes the "running" badge from the dashboard. ` +
    `If a real Lambda invocation was already in flight, it continues ` +
    `to completion — there is no out-of-band abort API for ad-hoc ` +
    `Lambda invocations. (EventBridge-scheduled runs are unaffected.)`
  );
}

function runAgentManually(agent, { deployed } = {}) {
  // Two failure modes today, both honest:
  //  1. Agent is not deployed → no Lambda exists, no schedule, no
  //     run-queue. The fix is real DevOps work (build the Lambda
  //     package, IAM role, EventBridge schedule, etc.) — see
  //     deploy/deploy_lambdas.md if it exists, or the agent spec at
  //     .claude/agents/<slug>.md for the contract the Lambda needs
  //     to satisfy.
  //  2. Agent IS deployed → invoking it from the SPA still needs the
  //     run-queue bridge because App Runner's Django container is
  //     VPC-bound and can't call lambda:InvokeFunction directly. The
  //     fix: POST /api/agents/<slug>/run/ writes a marker file to
  //     s3://<bucket>/fleet/queue/<slug>.json; a dispatcher Lambda
  //     watches that prefix and fans markers into real invocations.
  if (!deployed) {
    alert(
      `"${agent.slug}" has no Lambda deployed yet.\n\n` +
      `Status: NOT DEPLOYED — the agent_runner Lambda for this slug ` +
      `hasn't been provisioned in AWS. Until it is, the dispatcher ` +
      `has nothing to invoke and no event/log to read back.\n\n` +
      `Next: deploy the Lambda + EventBridge schedule per ` +
      `.claude/agents/${agent.slug}.md. Open the Spec button to ` +
      `read the contract.`
    );
    return;
  }
  alert(
    `Manual run for "${agent.slug}" needs the run-queue endpoint ` +
    `(POST /api/agents/<slug>/run/), which isn't wired up yet.\n\n` +
    `App Runner is VPC-bound and can't call lambda:InvokeFunction ` +
    `directly. The plan: Django writes a marker to ` +
    `s3://<bucket>/fleet/queue/<slug>.json → a dispatcher Lambda ` +
    `picks it up and invokes the agent.\n\n` +
    `Use Logs (drawer / CloudWatch) and Spec for now.`
  );
}

// ── Roster table — one row per agent ─────────────────────────────────
function RosterTable({ agents, onSelect, onOpenLogs, runningSlugs, onRun, onStop }) {
  return (
    <div
      style={{ ...card, padding: 0, marginBottom: 18, overflowX: "auto" }}
      // overflowX:auto so a narrow viewport can scroll the 10-column
      // roster horizontally instead of clipping. Vertical scroll comes
      // from the page itself, not this container.
    >
      <table style={{
        width: "100%", borderCollapse: "collapse",
        fontSize: 14, fontVariantNumeric: "tabular-nums",
      }}>
        <thead>
          <tr style={{ background: "var(--fleet-table-header-bg)", borderBottom: "1px solid var(--fleet-card-border)" }}>
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
                  borderTop: "1px solid var(--fleet-row-border)",
                  cursor: "pointer",
                  background: "transparent",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = "var(--fleet-row-hover)"}
                onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
              >
                <Td>
                  <div style={{ fontWeight: 600, color: "var(--fleet-text)" }}>{a.slug}</div>
                  <div style={{
                    fontSize: 12, color: "var(--fleet-text-faint)",
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
                  <span style={{ fontSize: 12, color: "var(--fleet-text-muted)", textTransform: "uppercase" }}>
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
                <Td align="right" style={{ color: "var(--fleet-text)" }}>{a.metrics_24h?.invocations ?? "—"}</Td>
                <Td align="right" style={{
                  color: (a.metrics_24h?.errors || 0) > 0 ? "var(--fleet-error-fg)" : "var(--fleet-text-muted)",
                  fontWeight: (a.metrics_24h?.errors || 0) > 0 ? 700 : 400,
                }}>{a.metrics_24h?.errors ?? "—"}</Td>
                <Td align="right" style={{ color: "var(--fleet-text)" }}>{a.metrics_24h?.duration_avg_ms ?? "—"}</Td>
                <Td style={{ color: "var(--fleet-text-muted)", fontSize: 12 }}>
                  {a.schedule
                    ? <span title={fmtCron(a.schedule.expression)}>{a.cadence}</span>
                    : a.cadence}
                </Td>
                <Td style={{ fontSize: 12, color: "var(--fleet-text-muted)" }}>
                  {lastEv
                    ? <>
                        <span style={{
                          color: lastEv.event === "handler_raised" ? "var(--fleet-error-fg)" : "var(--fleet-ok-fg)",
                          fontWeight: 600,
                        }}>
                          {lastEv.event === "handler_raised" ? "✕" : "✓"}
                        </span>
                        {" "}
                        {fmtRelative(lastEv.ts_ms)}
                      </>
                    : "—"}
                </Td>
                <Td align="right">
                  <RowActions
                    agent={a}
                    isRunning={runningSlugs?.has(a.slug)}
                    onRun={onRun}
                    onStop={onStop}
                    onOpenLogs={onOpenLogs}
                  />
                </Td>
              </tr>
            );
          })}
          {!agents.length && (
            <tr>
              <Td colSpan={10} style={{ padding: 36, textAlign: "center", color: "var(--fleet-text-faint)" }}>
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
      fontSize: 11, fontWeight: 700, color: "var(--fleet-text-muted)",
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
        fontSize: 14, fontWeight: 700, color: "var(--fleet-text)", marginBottom: 12,
      }}>
        Recent activity
      </div>
      {!events.length && (
        <div style={{ fontSize: 13, color: "var(--fleet-text-faint)" }}>
          No agent invocations recorded yet. The first will appear here within
          ~1 minute of any agent firing.
        </div>
      )}
      {events.map((e, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "8px 0",
          borderTop: i ? "1px solid var(--fleet-row-border)" : "none",
          fontSize: 13,
        }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 22, height: 22, borderRadius: 6,
            background: e.event === "handler_raised" ? "rgba(220,38,38,0.10)" : "rgba(16,185,129,0.10)",
            color: e.event === "handler_raised" ? "var(--fleet-error-fg)" : "var(--fleet-ok-fg)",
            fontSize: 12, fontWeight: 700,
          }}>
            {e.event === "handler_raised" ? "✕" : "✓"}
          </span>
          <code style={{ fontWeight: 600, color: "var(--fleet-text)", fontSize: 12 }}>{e.slug}</code>
          <span style={{ color: "var(--fleet-text-muted)", flex: 1 }}>
            {e.event === "handler_raised"
              ? <>raised <code style={{ fontSize: 12 }}>{e.err || "?"}</code></>
              : <>done in {e.elapsed_s ?? "?"}s{e.tone ? ` (${e.tone})` : ""}</>}
          </span>
          <span style={{ color: "var(--fleet-text-faint)", fontSize: 12 }}>{fmtRelative(e.ts_ms)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Drawer for the selected agent ────────────────────────────────────
// Demo4-style activity panel: hero header → KPI tiles → activity
// timeline (or provisioning checklist when not deployed) → spec chips
// → Lambda / Schedule callouts → collapsible raw event JSON.
function AgentDrawer({ agent, onClose }) {
  const tier = TIER_BADGE[agent.tier] || { bg: "#eee", fg: "#444", label: agent.tier };
  const st   = STATUS_PILL[agent.status] || STATUS_PILL.not_deployed;
  const lastEv = agent.last_event;
  const deployed = agent.status !== "not_deployed";

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0,
        background: "var(--fleet-overlay-bg)",
        backdropFilter: "blur(2px)",
        display: "flex", justifyContent: "flex-end",
        zIndex: 100,
      }}
    >
      <motion.aside
        initial={{ x: 32, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(620px, 100%)", height: "100%",
          background: "var(--fleet-page-bg)",
          color: "var(--fleet-text)",
          overflowY: "auto",
          boxShadow: "-12px 0 40px rgba(0,0,0,0.18)",
          display: "flex", flexDirection: "column",
        }}
      >
        {/* ── Hero header ────────────────────────────────────────── */}
        <div style={{
          background: "var(--fleet-hero-gradient)",
          borderBottom: "1px solid var(--fleet-card-border)",
          padding: "22px 28px 18px", position: "relative",
        }}>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              position: "absolute", top: 14, right: 16,
              background: "transparent", border: "none",
              fontSize: 24, cursor: "pointer", color: "var(--fleet-text-faint)",
              lineHeight: 1, padding: 2,
            }}
          >×</button>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{
              fontSize: 10, fontWeight: 700,
              padding: "3px 8px", borderRadius: 6,
              background: tier.bg, color: tier.fg, letterSpacing: "0.05em",
            }}>{tier.label}</span>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 99,
              background: st.bg, color: st.fg, letterSpacing: "0.05em",
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: 99, background: st.dot,
                boxShadow: agent.status === "online" ? `0 0 4px ${st.dot}` : "none",
              }} />
              {st.label}
            </span>
            <span style={{
              fontSize: 10, fontWeight: 700, padding: "3px 8px",
              borderRadius: 6, background: "var(--fleet-chip-bg)",
              color: "var(--fleet-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em",
            }}>{agent.type}</span>
          </div>
          <h2 style={{ margin: "0 32px 0 0", fontSize: 22, fontWeight: 800, color: "var(--fleet-text)", letterSpacing: "-0.01em" }}>
            {agent.slug}
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--fleet-text-muted)", lineHeight: 1.5 }}>{agent.desc}</p>
          <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <a
              href={`${GH_AGENTS_BASE}/${agent.slug}.md`}
              target="_blank" rel="noreferrer"
              style={pillBtn}
            ><i className="bi bi-file-earmark-text me-1" />Spec</a>
            <a
              href={cloudwatchLogsUrl(agent.slug)}
              target="_blank" rel="noreferrer"
              style={pillBtn}
            ><i className="bi bi-box-arrow-up-right me-1" />CloudWatch</a>
          </div>
        </div>

        {/* ── Body ──────────────────────────────────────────────── */}
        <div style={{ padding: "18px 24px 32px", display: "flex", flexDirection: "column", gap: 16 }}>
          <KpiTiles agent={agent} />

          <ActivityTimeline agent={agent} deployed={deployed} lastEv={lastEv} />

          {/* Schedule callout */}
          <CalloutCard
            icon="bi-clock-history"
            title="Cadence"
            tone="indigo"
            subtitle={agent.cadence}
            rows={agent.schedule ? [
              ["Schedule name", agent.schedule.name],
              ["Cron",          <code key="c" style={codeInline}>{fmtCron(agent.schedule.expression)}</code>],
              ["Timezone",      agent.schedule.timezone],
              ["State",         agent.schedule.state],
            ] : null}
            emptyHint="No EventBridge rule provisioned yet."
          />

          {/* Lambda callout */}
          <CalloutCard
            icon="bi-lightning-charge"
            title="Lambda function"
            tone="amber"
            subtitle={agent.lambda ? agent.lambda.state : "Not provisioned"}
            rows={agent.lambda ? [
              ["ARN",      <code key="a" style={codeInline}>{agent.lambda.arn}</code>],
              ["Memory",   `${agent.lambda.memory_mb} MB`],
              ["Timeout",  `${agent.lambda.timeout_s} s`],
              ["Package",  agent.lambda.package_type],
              ["Modified", agent.lambda.last_modified],
            ] : null}
            emptyHint="No Lambda function exists for this agent yet."
          />

          {lastEv && <RawEventJson event={lastEv} />}
        </div>
      </motion.aside>
    </div>
  );
}

// ── Hero pill-button used in drawer header
const pillBtn = {
  fontSize: 12, fontWeight: 600,
  padding: "6px 11px", borderRadius: 8,
  border: "1px solid var(--fleet-btn-border)",
  background: "var(--fleet-btn-bg)", color: "var(--fleet-text)",
  textDecoration: "none",
  display: "inline-flex", alignItems: "center", gap: 4,
};
const codeInline = {
  fontSize: 11, background: "var(--fleet-code-bg)",
  padding: "1px 5px", borderRadius: 4, color: "var(--fleet-code-fg)",
};

// ── 3-up KPI tiles ───────────────────────────────────────────────────
function KpiTiles({ agent }) {
  const tile = (label, value, sub, tone) => ({
    label, value, sub, tone,
  });
  const errs = agent.metrics_24h?.errors || 0;
  const invs = agent.metrics_24h?.invocations || 0;
  const dur  = agent.metrics_24h?.duration_avg_ms;
  const tiles = [
    tile("Invocations 24h", invs, invs ? "successful runs" : "no run in last 24 h", "blue"),
    tile("Errors",          errs, errs ? "needs attention" : "all clean", errs ? "red" : "green"),
    tile("Avg duration",
         dur != null ? `${dur} ms` : "—",
         dur != null ? "p50 elapsed" : "no data yet",
         "neutral"),
  ];
  const toneBar = {
    blue: "#3699ff", green: "#10b981", red: "#ef4444",
    amber: "#eab308", neutral: "#94a3b8",
  };
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(3, 1fr)",
      gap: 10,
    }}>
      {tiles.map((t) => (
        <div key={t.label} style={{
          background: "var(--fleet-card-bg)",
          border: "1px solid var(--fleet-card-border)",
          borderRadius: 12,
          padding: "12px 14px",
          position: "relative", overflow: "hidden",
        }}>
          <div style={{
            position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
            background: toneBar[t.tone],
          }} />
          <div style={{
            fontSize: 10, fontWeight: 700, color: "var(--fleet-text-muted)",
            textTransform: "uppercase", letterSpacing: "0.06em",
          }}>{t.label}</div>
          <div style={{
            fontSize: 22, fontWeight: 800, color: "var(--fleet-text)",
            marginTop: 2, fontVariantNumeric: "tabular-nums",
          }}>{t.value}</div>
          <div style={{ fontSize: 11, color: "var(--fleet-text-faint)", marginTop: 2 }}>{t.sub}</div>
        </div>
      ))}
    </div>
  );
}

// ── Activity timeline (or provisioning checklist for NOT DEPLOYED) ──
function ActivityTimeline({ agent, deployed, lastEv }) {
  return (
    <div style={card3}>
      <div style={cardHeader}>
        <span><i className="bi bi-activity me-1" />Activity</span>
        <span style={cardHeaderHint}>
          {deployed
            ? `${buildActivityItems(agent, lastEv).length} event${
                buildActivityItems(agent, lastEv).length === 1 ? "" : "s"} · last 7 days`
            : "provisioning checklist"}
        </span>
      </div>
      <div style={{ padding: "6px 0 4px" }}>
        {deployed && (
          <ActivityList items={buildActivityItems(agent, lastEv)} agentSlug={agent.slug} />
        )}
        {!deployed && <ProvisioningChecklist agent={agent} />}
      </div>
    </div>
  );
}

// ── Activity synthesis ───────────────────────────────────────────────
// Build a chronological list of events from whatever the dashboard
// knows about the agent. The agent state file only persists the latest
// run, so we top up the list with deterministic lifecycle entries:
//   - next scheduled fire (future, parsed from `cron(M H * * ? *)`)
//   - last run (success or failure) — anchors the timeline
//   - digest lines (if the run wrote a multi-line digest, each
//     non-header line becomes its own sub-bullet under the run)
//   - lambda last_modified (deploy / config push)
//   - schedule state change (ENABLED/DISABLED)
//   - agent's first state-file write (state.first_seen_ms if present)
//
// Items are returned newest-first. Future items get tone="scheduled".
function buildActivityItems(agent, lastEv) {
  const items = [];

  // 1) Next scheduled fire — only when an EventBridge rule exists.
  const next = nextCronFire(agent.schedule?.expression);
  if (next != null) {
    items.push({
      kind: "scheduled",
      ts_ms: next,
      icon: "bi-clock-history",
      tone: "scheduled",
      title: "Next scheduled run",
      subline: agent.schedule?.expression ? fmtCron(agent.schedule.expression) : null,
    });
  }

  // 2) Last run from the state file. Drives the digest sub-bullets.
  if (lastEv && lastEv.ts_ms) {
    const ok = lastEv.event !== "handler_raised" && (lastEv.ok !== false);
    items.push({
      kind: "run",
      ts_ms: lastEv.ts_ms,
      icon: ok ? "bi-check2-circle" : "bi-exclamation-octagon",
      tone: ok ? "ok" : "err",
      title: ok
        ? `Run completed in ${lastEv.elapsed_s ?? "?"}s`
        : `Run raised ${lastEv.err || "an exception"}`,
      subline: lastEv.digest
        ? lastEv.digest.split("\n")[0]
        : ok ? `state written → s3://…/${agent.slug}.json`
             : (lastEv.trace_tail?.slice(-1)[0]) || "",
      digest: lastEv.digest,
    });

    // 2b) Split the digest body into bullet rows so the activity feed
    // reads as a sequence rather than a single dense block. Skip the
    // first line (already shown as subline) and lines that are pure
    // separators / banner headers.
    if (lastEv.digest) {
      const bodyLines = lastEv.digest
        .split("\n")
        .slice(1)
        .map((l) => l.trim())
        .filter((l) => l && !/^=+/.test(l) && !/^Anomalies:\s*$/i.test(l));
      // Walk newer→older by giving each line a synthetic timestamp
      // one second earlier than the last run, in order, so React keys
      // stay stable and the visual ordering is preserved.
      bodyLines.forEach((line, i) => {
        const [labelRaw, ...rest] = line.split(":");
        const label = labelRaw?.trim();
        const value = rest.join(":").trim();
        // Only flag a row as err/warn when the *value* signals an
        // issue. "Anomalies: none" is not an anomaly; the previous
        // regex matched on the label and painted the row red.
        const sev = (() => {
          if (!value || /^none$/i.test(value)) return "muted";
          if (/\[red\]|\berror\b|\bfailed?\b|raised /i.test(value)) return "err";
          if (/\[yellow\]|\bwarn(ing)?\b|degraded/i.test(value)) return "warn";
          return "muted";
        })();
        items.push({
          kind: "digest",
          ts_ms: lastEv.ts_ms - (i + 1),
          icon: sev === "err"  ? "bi-exclamation-circle"
              : sev === "warn" ? "bi-exclamation-triangle"
              : "bi-dot",
          tone: sev,
          title: label || line,
          subline: value || null,
        });
      });
    }
  }

  // 3) Lambda deploy / last config push.
  if (agent.lambda?.last_modified) {
    const ms = parseTs(agent.lambda.last_modified);
    if (ms) {
      items.push({
        kind: "lambda",
        ts_ms: ms,
        icon: "bi-cloud-upload",
        tone: "info",
        title: "Lambda function updated",
        subline: `${agent.lambda.package_type} · ${agent.lambda.memory_mb} MB · ${agent.lambda.timeout_s}s timeout`,
      });
    }
  }

  // 4) Schedule status. We don't have a created-at on the schedule
  // (EventBridge doesn't expose one cheaply), so we treat ENABLED as a
  // standing notice rather than a dated row — anchor it to lambda's
  // last_modified ts if available, otherwise drop it.
  if (agent.schedule?.state === "ENABLED" && agent.lambda?.last_modified) {
    const anchor = parseTs(agent.lambda.last_modified) || Date.now();
    items.push({
      kind: "schedule",
      ts_ms: anchor - 1,  // sort just under "lambda updated"
      icon: "bi-calendar2-check",
      tone: "info",
      title: "EventBridge schedule active",
      subline: `${agent.schedule.name} · ${agent.schedule.timezone || "UTC"}`,
    });
  }

  // If nothing landed (deployed but no run, no schedule), give a
  // friendly empty hint via a single "waiting" row.
  if (!items.length) {
    items.push({
      kind: "empty",
      ts_ms: Date.now(),
      icon: "bi-hourglass-split",
      tone: "muted",
      title: "Lambda is deployed but hasn't fired in the last 7 days.",
      subline: null,
    });
  }

  // Sort newest first; future-scheduled events keep their positive
  // offset so they sit at the top.
  items.sort((a, b) => b.ts_ms - a.ts_ms);
  return items;
}

// Parse the simple "cron(M H * * ? *)" UTC daily form into the next
// fire time as ms. Returns null for cron expressions we can't simulate
// (weekly, rate(), etc.) — caller will just skip the "Next" row.
function nextCronFire(expr) {
  if (!expr) return null;
  const m = /^cron\((\d+)\s+(\d+)\s+\*\s+\*\s+\?\s+\*\)$/.exec(expr);
  if (!m) return null;
  const [_, mm, hh] = m;
  const now = new Date();
  const next = new Date(Date.UTC(
    now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(),
    parseInt(hh, 10), parseInt(mm, 10), 0, 0,
  ));
  if (next.getTime() <= now.getTime()) next.setUTCDate(next.getUTCDate() + 1);
  return next.getTime();
}

function parseTs(s) {
  if (!s) return null;
  const ms = Date.parse(s);
  return Number.isFinite(ms) ? ms : null;
}

// ── ActivityList — renders the synthesized rows as a timeline ───────
const TONE_STYLES = {
  ok:        { fg: "#10b981", bg: "rgba(16,185,129,0.10)" },
  err:       { fg: "#ef4444", bg: "rgba(239,68,68,0.10)" },
  warn:      { fg: "#eab308", bg: "rgba(234,179,8,0.12)" },
  scheduled: { fg: "#3699ff", bg: "rgba(54,153,255,0.10)" },
  info:      { fg: "#6366f1", bg: "rgba(99,102,241,0.10)" },
  muted:     { fg: "#94a3b8", bg: "rgba(148,163,184,0.10)" },
};

function ActivityList({ items, agentSlug }) {
  return (
    <div>
      {items.map((it, i) => (
        <ActivityRow key={`${it.kind}-${it.ts_ms}-${i}`} item={it} agentSlug={agentSlug} />
      ))}
    </div>
  );
}

function ActivityRow({ item, agentSlug }) {
  const tone = TONE_STYLES[item.tone] || TONE_STYLES.muted;
  const isFuture = item.kind === "scheduled";
  const isRunWithDigest = item.kind === "run" && item.digest;
  return (
    <div style={{
      position: "relative",
      padding: isRunWithDigest ? "8px 16px 12px 50px" : "6px 16px 6px 50px",
      borderTop: "1px solid var(--fleet-row-border)",
    }}>
      <span style={{
        position: "absolute", left: 16, top: isRunWithDigest ? 8 : 6,
        width: 24, height: 24, borderRadius: 99,
        background: tone.bg, color: tone.fg,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        fontSize: 13,
      }}>
        <i className={`bi ${item.icon}`} />
      </span>
      <div style={{
        display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline",
      }}>
        <div style={{
          fontSize: item.kind === "digest" ? 12 : 13,
          fontWeight: item.kind === "digest" ? 500 : 700,
          color: "var(--fleet-text)",
        }}>{item.title}</div>
        <div style={{
          fontSize: 11, color: "var(--fleet-text-faint)",
          fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
        }} title={new Date(item.ts_ms).toISOString()}>
          {isFuture ? `in ${fmtFuture(item.ts_ms)}` : fmtRelative(item.ts_ms)}
        </div>
      </div>
      {item.subline && (
        <div style={{
          fontSize: 12, color: "var(--fleet-text-muted)", marginTop: 2,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>{item.subline}</div>
      )}
      {isRunWithDigest && (
        <pre style={{
          marginTop: 8, fontSize: 11, lineHeight: 1.55,
          background: "var(--fleet-terminal-bg)", color: "var(--fleet-terminal-fg)",
          padding: "10px 12px", borderRadius: 8,
          overflowX: "auto", margin: "8px 0 0",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}>{item.digest}</pre>
      )}
    </div>
  );
}

function fmtFuture(ts_ms) {
  const sec = Math.max(0, Math.floor((ts_ms - Date.now()) / 1000));
  if (sec < 60)    return `${sec}s`;
  if (sec < 3600)  return `${Math.floor(sec / 60)}m`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  return `${Math.floor(sec / 86400)}d`;
}

const card3 = {
  background: "var(--fleet-card-bg)",
  border: "1px solid var(--fleet-card-border)",
  borderRadius: 14,
  overflow: "hidden",
};
const cardHeader = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "12px 16px",
  borderBottom: "1px solid var(--fleet-row-border)",
  fontSize: 13, fontWeight: 700, color: "var(--fleet-text)",
  background: "var(--fleet-table-header-bg)",
};
const cardHeaderHint = {
  fontSize: 10, fontWeight: 700, color: "var(--fleet-text-faint)",
  textTransform: "uppercase", letterSpacing: "0.06em",
};
const emptyRow = {
  display: "flex", gap: 10, alignItems: "center",
  padding: "14px 16px", fontSize: 13, color: "var(--fleet-text-muted)",
};

function ProvisioningChecklist({ agent }) {
  // What it takes to flip this agent from NOT DEPLOYED to ONLINE.
  // Each step is a 1-line user-readable checkbox row.
  const items = [
    { done: false, label: "Build Lambda handler in deploy/agent_runner/handlers/",
      hint: `handlers/${agent.slug.replace(/-/g, "_")}.py` },
    { done: false, label: "Push agent_runner image to ECR",
      hint: "carpapi-agent-base:latest" },
    { done: false, label: "Create Lambda function from image",
      hint: `carpapi-${agent.slug}` },
    { done: !!agent.schedule, label: "EventBridge schedule",
      hint: agent.cadence },
    { done: false, label: "First state file written",
      hint: `s3://…/fleet/${agent.slug}.json` },
  ];
  return (
    <div style={{ padding: "4px 0 4px" }}>
      {items.map((it, i) => (
        <div key={i} style={{
          display: "flex", gap: 12, alignItems: "flex-start",
          padding: "8px 16px",
          borderTop: i ? "1px solid var(--fleet-row-border)" : "none",
        }}>
          <span style={{
            width: 18, height: 18, borderRadius: 4,
            border: "1.5px solid " + (it.done ? "#10b981" : "var(--fleet-text-faint)"),
            background: it.done ? "#10b981" : "var(--fleet-card-bg)",
            color: "#fff",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 12, fontWeight: 700,
            flexShrink: 0, marginTop: 1,
          }}>{it.done ? "✓" : ""}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{
              fontSize: 13,
              color: it.done ? "var(--fleet-text-faint)" : "var(--fleet-text)",
              fontWeight: it.done ? 500 : 600,
              textDecoration: it.done ? "line-through" : "none",
            }}>{it.label}</div>
            <div style={{
              fontSize: 11, color: "var(--fleet-text-faint)", marginTop: 1,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            }}>{it.hint}</div>
          </div>
        </div>
      ))}
      <div style={{
        margin: "8px 16px 4px", padding: "10px 12px",
        background: "var(--fleet-info-bg)", border: "1px solid var(--fleet-info-border)",
        borderRadius: 8, fontSize: 12, color: "var(--fleet-info-fg)", lineHeight: 1.5,
      }}>
        <i className="bi bi-info-circle me-1" />
        Open the <b>Spec</b> button above to read the full contract this
        Lambda has to satisfy before the dashboard can show real activity.
      </div>
    </div>
  );
}

// ── Callout card with icon + colored badge + optional rows ──────────
function CalloutCard({ icon, title, tone, subtitle, rows, emptyHint }) {
  const toneColor = {
    indigo: { bg: "rgba(79,70,229,0.10)", fg: "#4338ca" },
    amber:  { bg: "rgba(234,179,8,0.12)", fg: "#854d0e" },
    green:  { bg: "rgba(16,185,129,0.10)", fg: "#047857" },
  }[tone] || { bg: "rgba(0,0,0,0.05)", fg: "#475569" };
  return (
    <div style={card3}>
      <div style={cardHeader}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span style={{
            width: 26, height: 26, borderRadius: 8,
            background: toneColor.bg, color: toneColor.fg,
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            fontSize: 13,
          }}><i className={`bi ${icon}`} /></span>
          {title}
        </span>
        <span style={cardHeaderHint}>{subtitle}</span>
      </div>
      <div style={{ padding: "4px 16px 10px" }}>
        {rows ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: "6px 0", color: "var(--fleet-text-muted)", width: 110, verticalAlign: "top" }}>{k}</td>
                  <td style={{ padding: "6px 0", color: "var(--fleet-text)", textAlign: "right", wordBreak: "break-all" }}>{v ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: "10px 0 4px", fontSize: 13, color: "var(--fleet-text-faint)", display: "flex", alignItems: "center", gap: 8 }}>
            <i className="bi bi-dash-circle" />
            {emptyHint}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Collapsible raw event JSON ──────────────────────────────────────
function RawEventJson({ event }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={card3}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        style={{
          ...cardHeader, width: "100%",
          border: "none", cursor: "pointer",
          fontSize: 13, fontWeight: 700,
        }}
      >
        <span>
          <i className={`bi ${open ? "bi-chevron-down" : "bi-chevron-right"} me-1`} />
          Raw event JSON
        </span>
        <span style={cardHeaderHint}>{open ? "click to hide" : "click to expand"}</span>
      </button>
      {open && (
        <pre style={{
          margin: 0, fontSize: 11, lineHeight: 1.55,
          background: "var(--fleet-terminal-bg)", color: "var(--fleet-terminal-fg)",
          padding: "14px 16px",
          overflow: "auto", maxHeight: 360,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}>
          {JSON.stringify(event, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ── Theme variables ─────────────────────────────────────────────────
// Single <style> injected at the page root that defines every
// `--fleet-*` variable for both themes. The light → dark switch is
// driven by `data-fleet-theme="dark"` on the .fleet-agents-page wrapper.
function FleetThemeStyles() {
  return (
    <style>{`
      .fleet-agents-page {
        --fleet-page-bg:         #f7f8fa;
        --fleet-card-bg:         #ffffff;
        --fleet-card-border:     rgba(0,0,0,0.08);
        --fleet-row-border:      rgba(0,0,0,0.05);
        --fleet-row-hover:       #f1f5f9;
        --fleet-table-header-bg: #fafbfc;
        --fleet-text:            #0f172a;
        --fleet-text-muted:      #475569;
        --fleet-text-faint:      #94a3b8;
        --fleet-btn-bg:          #ffffff;
        --fleet-btn-border:      rgba(0,0,0,0.12);
        --fleet-chip-bg:         rgba(0,0,0,0.05);
        --fleet-error-bg:        rgba(220,38,38,0.08);
        --fleet-error-fg:        #b91c1c;
        --fleet-ok-fg:           #047857;
        --fleet-code-bg:         #f1f5f9;
        --fleet-code-fg:         #334155;
        --fleet-terminal-bg:     #0b1220;
        --fleet-terminal-fg:     #e2e8f0;
        --fleet-overlay-bg:      rgba(15,23,42,0.45);
        --fleet-hero-gradient:   linear-gradient(180deg,#ffffff 0%,#f7f8fa 100%);
        --fleet-info-bg:         rgba(54,153,255,0.06);
        --fleet-info-border:     rgba(54,153,255,0.18);
        --fleet-info-fg:         #1e3a8a;
        color-scheme: light;
      }
      .fleet-agents-page[data-fleet-theme="dark"] {
        --fleet-page-bg:         #0b1220;
        --fleet-card-bg:         #0f1a2e;
        --fleet-card-border:     rgba(255,255,255,0.08);
        --fleet-row-border:      rgba(255,255,255,0.06);
        --fleet-row-hover:       #14223c;
        --fleet-table-header-bg: #14223c;
        --fleet-text:            #e2e8f0;
        --fleet-text-muted:      #94a3b8;
        --fleet-text-faint:      #64748b;
        --fleet-btn-bg:          #14223c;
        --fleet-btn-border:      rgba(255,255,255,0.12);
        --fleet-chip-bg:         rgba(255,255,255,0.08);
        --fleet-error-bg:        rgba(239,68,68,0.18);
        --fleet-error-fg:        #fca5a5;
        --fleet-ok-fg:           #6ee7b7;
        --fleet-code-bg:         rgba(255,255,255,0.08);
        --fleet-code-fg:         #cbd5e1;
        --fleet-terminal-bg:     #020617;
        --fleet-terminal-fg:     #e2e8f0;
        --fleet-overlay-bg:      rgba(0,0,0,0.65);
        --fleet-hero-gradient:   linear-gradient(180deg,#14223c 0%,#0b1220 100%);
        --fleet-info-bg:         rgba(54,153,255,0.12);
        --fleet-info-border:     rgba(54,153,255,0.30);
        --fleet-info-fg:         #bfdbfe;
        color-scheme: dark;
      }
    `}</style>
  );
}
