# Fleet Console — UI kit

The interactive **CarPapi Fleet Console** — a 16-bit JRPG party-screen
take on a software-agent management dashboard. 14 agents arranged
across 5 tiers, with live status LEDs, HP/XP/quota meters,
pixel sprite portraits, a 24-hour schedule strip, and a VT323
activity log.

## Files

| File | Role |
|---|---|
| `index.html` | Entry — full single-page console with React + Babel |
| `agents.js` | The 14-agent dataset (callsigns, tiers, descriptions, schedules) — lifted from `.claude/agents/*.md` |
| `sprites.jsx` | `<Sprite>` component — renders a 12×12 pixel-grid SVG with a per-tier palette |
| `components.jsx` | `<AgentCard>`, `<Sidebar>`, `<Header>`, `<LogFeed>`, `<ScheduleStrip>`, `<MeterBar>`, `<DialogBox>` |

## Screens

- **Roster** (default) — 14 agent cards in a grid, grouped or
  flat-sorted, sidebar filters by tier.
- **Detail** — click any card → modal with full playbook + recent runs
  + safety boundaries.
- **Summon** — bottom-right command palette, type a phrase
  (`rescrape performance-ford`, `audit data`) → confirms the agent
  and parameters.

## Interaction notes

- Click an agent card to open detail.
- Click a sidebar tier to filter.
- The activity log is **fake-live**: a `setInterval` appends a new
  event every 2–4s, drawn from a pool of agent-realistic strings.
- Buttons depress 2px and lose their inset highlight on `:active` —
  see `.px-btn` in `colors_and_type.css`.

## What this is and isn't

This is a **visual + interaction prototype**. The agent management
backend doesn't exist yet — the agent specs in `.claude/agents/`
define the behaviour and the EventBridge schedule, but no real
dashboard is wired up. Treat this kit as a forward-looking design
artifact, faithful to the agent roster + tier system but not driven
by live data.
