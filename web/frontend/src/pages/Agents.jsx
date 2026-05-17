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
import { getAgents, runAgent } from "../api.js";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";
import { useTheme } from "../theme.jsx";

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

// Status pills the table + drawer render. We deliberately collapse
// the backend's `online | idle | degraded | failed | not_deployed`
// taxonomy into just two user-facing buckets — RUNNING and STOPPED —
// because the user wants the page to read like the right-side task
// stream: an agent is either currently doing something or it isn't.
//
// `failed` is preserved as a separate pill (red) so a known-broken
// agent doesn't masquerade as merely "stopped" — that signal is too
// important to fold away.
const STATUS_PILL = {
  running:      { bg: "rgba(16,185,129,0.12)", fg: "#047857", label: "RUNNING", dot: "#10b981" },
  stopped:      { bg: "rgba(100,116,139,0.10)", fg: "#475569", label: "STOPPED", dot: "#94a3b8" },
  failed:       { bg: "rgba(220,38,38,0.10)",  fg: "#b91c1c", label: "FAILED",  dot: "#ef4444" },
};

// An agent is considered RUNNING if either:
//   (a) the user just clicked ▶ Run and we're awaiting the next state
//       publish (tracked in the local `running` map), OR
//   (b) it published a fresh state within the last RUN_RECENCY_MS —
//       which for the 5-quality-agent loop fires every ~30 s, so a 5
//       min window lights them up steadily during a continuous run
//       and lets them lapse back to STOPPED a few minutes after the
//       loop pauses.
const RUN_RECENCY_MS = 5 * 60 * 1000;
function runStatus(agent, running) {
  if (running && running[agent.slug]) return "running";
  if (agent.status === "failed") return "failed";
  const ts = agent.last_event?.ts_ms;
  if (ts && Date.now() - ts <= RUN_RECENCY_MS) return "running";
  return "stopped";
}

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
            <KpiStrip
              summary={summary}
              successRate={successRate}
              // Same running-recency rule the roster row uses, so the
              // "Agents running" tile and each row's status pill agree.
              runningCount={agents.reduce(
                (n, a) => n + (runStatus(a, running) === "running" ? 1 : 0),
                0,
              )}
              stoppedCount={agents.reduce(
                (n, a) => n + (runStatus(a, running) === "stopped" ? 1 : 0),
                0,
              )}
            />
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
        <AgentDrawer agent={selected} onClose={() => setSelectedSlug(null)} running={running} />
      )}

      {toast && <RunToast toast={toast} onDismiss={() => setToast(null)} />}

      {/* Compact footer — the 4-column marketing footer eats ~250 px
          at the bottom and obscures the bottom of the roster on a
          14-row table. Compact mode shows just © CarPapi · email in
          a single ~50 px bar. */}
      <PublicFooter compact />

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
function KpiStrip({ summary, successRate, runningCount = 0, stoppedCount = 0 }) {
  const items = [
    {
      label: "Agents running",
      value: `${runningCount} / ${summary.total || 0}`,
      sub: `${stoppedCount} stopped · ${summary.failed || 0} failed`,
      tone: runningCount >= 1 ? "green" : "neutral",
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

function RowActions({ agent, onRun, onOpenLogs, isRunning = false }) {
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
 *
 *  Uses the shared `runAgent()` helper from api.js so this picks up
 *  any future auth-header injection automatically (admin actions may
 *  one day need a bearer token).
 */
async function runAgentManually(agent, { onQueued, onError }) {
  try {
    const data = await runAgent(agent.slug, { reason: "dashboard-manual-run" });
    onQueued(data.queued_at_ms, data.queue_key);
  } catch (e) {
    const detail = e?.payload?.error || e?.payload?.detail || e?.message;
    onError(String(detail || e));
  }
}

// ── Roster table — one row per agent ─────────────────────────────────
function RosterTable({ agents, onSelect, onOpenLogs, onRun, running = {} }) {
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
            const rs = runStatus(a, running);
            const st = STATUS_PILL[rs] || STATUS_PILL.stopped;
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
                      // Glow only on RUNNING — gives a subtle "live"
                      // indicator without the noise of every row
                      // glowing.
                      boxShadow: rs === "running" ? `0 0 4px ${st.dot}` : "none",
                      animation: rs === "running"
                        ? "carpapi-pulse 1.6s ease-in-out infinite"
                        : "none",
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
                        color: lastEv.event === "handler_raised"
                          ? "var(--fleet-error-fg)"
                          : "var(--fleet-ok-fg)",
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
function AgentDrawer({ agent, onClose, running = {} }) {
  const tier = TIER_BADGE[agent.tier] || { bg: "#eee", fg: "#444", label: agent.tier };
  // Same RUNNING / STOPPED / FAILED mapping the roster row uses, so
  // opening the drawer doesn't surface a different status than what
  // the user just clicked on.
  const rs = runStatus(agent, running);
  const st = STATUS_PILL[rs] || STATUS_PILL.stopped;
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
                boxShadow: rs === "running" ? `0 0 4px ${st.dot}` : "none",
                animation: rs === "running"
                  ? "carpapi-pulse 1.6s ease-in-out infinite"
                  : "none",
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
// ── Run/Stop toast ──────────────────────────────────────────────────
// Non-blocking corner toast for async run-queue feedback. Pure CSS,
// theme-aware via the page's --fleet-* variables.
function RunToast({ toast, onDismiss }) {
  const palette = {
    ok:   { bg: "rgba(16,185,129,0.10)",  fg: "#047857", border: "rgba(16,185,129,0.30)" },
    err:  { bg: "rgba(220,38,38,0.10)",   fg: "#b91c1c", border: "rgba(220,38,38,0.30)" },
    info: { bg: "rgba(54,153,255,0.10)",  fg: "#1e40af", border: "rgba(54,153,255,0.30)" },
  }[toast.tone] || { bg: "var(--fleet-card-bg)", fg: "var(--fleet-text)", border: "var(--fleet-card-border)" };
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 12 }}
      style={{
        position: "fixed", right: 24, bottom: 24,
        maxWidth: 420,
        padding: "12px 16px 12px 14px", borderRadius: 12,
        background: palette.bg, color: palette.fg,
        border: `1px solid ${palette.border}`,
        fontSize: 13, lineHeight: 1.45,
        boxShadow: "0 12px 40px rgba(0,0,0,0.18)",
        display: "flex", alignItems: "flex-start", gap: 10,
        zIndex: 200, whiteSpace: "pre-line",
      }}
      role="status"
    >
      <i className={`bi ${toast.tone === "ok" ? "bi-check2-circle" : toast.tone === "err" ? "bi-exclamation-octagon" : "bi-info-circle"}`} style={{ fontSize: 16, marginTop: 1 }} />
      <span style={{ flex: 1 }}>{toast.msg}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{
          background: "transparent", border: "none", color: "inherit",
          cursor: "pointer", padding: 0, fontSize: 16, lineHeight: 1,
          opacity: 0.7,
        }}
      >×</button>
    </motion.div>
  );
}

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
