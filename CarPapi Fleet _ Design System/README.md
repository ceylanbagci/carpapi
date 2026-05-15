# CarPapi Fleet — Design System

A tactical, game-style design system for the **CarPapi operational
agent fleet**: 14 autonomous + interactive software agents that
manage scraping, enrichment, quality, cloud ops, and delivery for
CarPapi — a natural-language car search product (RAG over a
Postgres + pgvector listings DB, hosted on AWS).

This system extends the existing CarPapi web app's **"Demo4" theme**
(dark navy sidebar `#1e1e2d`, blue accent `#3699FF`) into a **16-bit
JRPG party-screen** for the fleet view: pixel sprites for each of the
14 agents, HP/XP meters, glowing status LEDs, scanline CRT texture,
hard-offset pixel shadows, and tier-coloured agent cards. The
typography is bitmap — **Press Start 2P** for HUD headlines,
**Silkscreen** for UI labels, **VT323** for the terminal activity
feed. Inter and JetBrains Mono are kept as long-form fallbacks.

## Source material

- **GitHub:** [ceylanbagci/carpapi](https://github.com/ceylanbagci/carpapi)
  — main repo, contains the web app, agent specs, and pipeline code.
  Explore further to recreate richer mocks.
- **Local mount:** `CarPapi/` — full codebase imported via the File
  System Access API. Key files referenced when building this system:
  - `web/frontend/src/styles/theme.css` — the Demo4 token source
  - `web/frontend/src/components/Sidebar.jsx`, `Header.jsx`, `Layout.jsx`
  - `.claude/agents/AGENTS.md` and the 14 individual `*.md` specs
  - `web/frontend/public/favicon.svg` — the CarPapi mark

The agent roster, tier names, cadence times, and agent
descriptions in this system are pulled verbatim from `AGENTS.md`.

---

## Index

| File | What it is |
|---|---|
| `README.md` | This document — context, foundations, manifest |
| `colors_and_type.css` | All design tokens (CSS variables) + font-face decls + element defaults |
| `fonts/` | Self-hosted Inter (400/500/600/700) + JetBrains Mono (400/500/700) |
| `assets/` | Logos, favicon, agent avatars (procedural, see kit) |
| `preview/` | Per-token preview cards (Type / Colors / Spacing / Components / Brand) — surfaced in the Design System tab |
| `ui_kits/fleet-console/` | The Agent Fleet Console UI kit — high-fidelity recreations of the dashboard, agent detail, mission timeline, and live ops feed |
| `SKILL.md` | Skill manifest, so this folder can be dropped into Claude Code as `carpapi-fleet-design` |

---

## Product context

CarPapi is a ChatGPT-like car-search product. Its core surface (the
web app, chat UI, dealer/listing tables) already exists. **What's
new — and what this design system is for** — is the operational
agent fleet: 14 agents in 5 tiers that turn the existing ad-hoc CLI
pipeline into a self-running system.

| Tier | Agents | Concern |
|---|---|---|
| **INGEST** | scraper-dispatcher, listing-validator, dedupe-sweeper, dealer-prospector | Raw data into Postgres |
| **ENRICH** | maker-enricher, maker-site-doctor | Manufacturer-site spec fill |
| **QUALITY** | scrape-watchdog, data-quality-auditor, price-anomaly-detector | Catch drift before it hits users |
| **CLOUD-OPS** | carpapi-deployer, rds-steward, aws-cost-sentinel | AWS / RDS / budget |
| **DELIVERY** | ci-cd-doctor, chat-quality-evaluator | Ship safely |

Each agent is **interactive** (summoned via Claude Code), **autonomous**
(EventBridge → Lambda on a daily schedule), or **dual**. The dashboard
needs to show, at a glance: who is alive, what they're doing now,
what just finished, what failed, and what's coming up.

The design metaphor is a **16-bit JRPG party-roster screen** —
each agent is an "operator" with a pixel-sprite portrait, an HP
bar (uptime), an XP bar (runs today), a callsign, and a tier band
at the top of the card. Think *FTL: Faster than Light* meets the
*Stardew Valley* social tab, rendered for production engineers.

---

## Content fundamentals

The voice borrows from the agent specs themselves (`.claude/agents/*.md`)
and the CarPapi marketing surface.

**Tone:** Confident, deadpan-technical, slightly playful. Engineer
peers talking — not customer-success cheerleading. Half-jokes are
allowed; emoji and exclamation points are not. The pixel-art
shell does NOT mean cutesy copy — the words stay terse and
operational. The game motif is in the visuals, not the voice.

**Person:** Mostly second person ("You are the foreman of CarPapi's
data ingestion.") or imperative ("Refuse — that's the dealer-prospector
agent's job."). Avoid first person plural except for shared-team
context ("we only scrape dealer-direct sites").

**Casing & punctuation:**
- Sentence case for everything except product names and agent
  callsigns (`scraper-dispatcher`, `aws-cost-sentinel` — always
  lowercase-kebab, always in mono).
- Tier names are uppercase tokens: `INGEST`, `ENRICH`, `QUALITY`,
  `CLOUD-OPS`, `DELIVERY`. Used as eyebrows and chips.
- "Em-dashes — like this — for asides."
- Numbers in copy: digits, not words ("14 agents", "3 tiers", "$100/mo").

**Vocabulary the brand uses:**
- *foreman*, *canary*, *cold-loop*, *quarantine*, *dispatch*,
  *summon*, *cadence*, *watchdog*, *steward*, *sentinel*, *doctor*
- *spec*, *runbook*, *playbook*, *boundary* (not "policy"),
  *autonomous / interactive / dual*
- *fleet* (never "team"), *mission* (never "task"),
  *digest* (the daily report), *trip* (an alarm)

**Vocabulary to avoid:** "AI-powered", "intelligent", "smart",
"seamless", "robust", "leverage", "synergize", emoji-as-bullet,
"🚀". Also avoid corporate fluff ("at scale", "going forward").

**Examples (real, lifted from `.claude/agents/`):**

> "You are the canary for manufacturer-website integrations. Maker
> sites change layouts without warning. When that happens, the
> maker-enricher agent fills `maker_specs` with wrong / partial data
> until someone notices. Your job is to notice the same day, freeze
> the adapter, and hand a precise reproducer to the dev who fixes it."

> "Refuse — that's the dealer-prospector agent's job."

> "12 anomalies, 11 likely scraper bugs, 1 real."

> "Newly paused: none."

**Emoji:** Never. The system uses Bootstrap Icons (already a CDN
dependency of the web app) and a small set of glyph LEDs (●○◐).

**Microcopy patterns:**
- Empty states: short, deadpan. `// no agents on cooldown.`
- Confirmations: `confirm: rescrape Performance Ford (87 URLs)?` — lowercase, colon, parens for scope.
- Errors: lead with the symptom, then the diagnostic. `HTTP 429 from
  ford.com — backing off 5m.`
- Status verbs are present-continuous: *scraping*, *enriching*,
  *deploying*, *waiting*, *blocked*.

---

## Visual foundations

### Palette

Five layers from black to gunmetal — `--bg-0` (`#0b0d14`) through
`--bg-5` (`#2f3144`). Demo4's `#1e1e2d` lands at `--bg-3` (cards).
The blue accent `#3699FF` is unchanged from the web app. Five
semantic colours (`ok`, `warn`, `danger`, `info`, `idle`) sit on top.
Five **tier hues** colour-code agents at a glance:

- `ingest` — blue (the brand accent)
- `enrich` — purple
- `quality` — cyan
- `cloud-ops` — amber
- `delivery` — pink

### Type

Five families, all self-hosted in `fonts/`:

- **Press Start 2P** — `--font-display` — NES-style chunky caps.
  Used for HUD titles, big stat numerals, dialog box headers. 28px
  for `--t-title`, 14px for `--t-subtitle`, 11px for `--t-hud`.
  Sparingly — it's loud.
- **Silkscreen** (400/700) — `--font-pixel` — the workhorse pixel
  UI font. Headings (`--t-h1` 20px, `--t-h2` 16px, `--t-h3` 13px),
  callsigns (11px uppercase tracked), button labels, body where
  pixel character matters (`--t-body-pixel` 13px).
- **VT323** — `--font-term` — a tall pixel monospace for terminal
  feeds and run output (`--t-body` 16px). Looks like a vintage
  CRT terminal.
- **Inter** (variable, 400–700) — `--font-sans` — fallback for
  long-form prose (README excerpts, multi-line agent descriptions
  where pixel fonts get tiring to read).
- **JetBrains Mono** — `--font-mono` — inline code, VINs, run hashes
  when bitmap pixels are too noisy.

Fonts are sourced from Google Fonts as variable woff2 files. Two
body scales live side-by-side: VT323 for the noisy terminal
aesthetic, Silkscreen for clean UI. Pick one per context.
See `colors_and_type.css` for the full token table.

### Spacing & radii

A 4px base scale (`--s-1` = 4 → `--s-10` = 72), aligned to pixel
grid. **Radii are 0 everywhere** — pixel art has no anti-aliased
curves. The only allowed "rounding" is the **stepped pixel notch**
(see `.px-notch` helper: a clip-path that cuts 4px triangles from
the four corners, giving a chunky JRPG dialog-box silhouette).

### Backgrounds

The console canvas is `--bg-1` (`#11131c`) with three optional
overlays stacked on top:

1. **`--scanlines`** — 1px white lines @ 2.5% opacity every 3px.
   Always-on for the dashboard. Gives the whole UI a CRT cast.
2. **`--vignette`** — radial edge-burn at 55% black. Applied to
   the dashboard body for that arcade-monitor falloff.
3. **Dither checker** — 8px conic-gradient checker between two
   adjacent bg layers, used for subtle pattern fills (e.g. empty
   inventory slots).

Gradients are otherwise banned in chrome — the only exception is
the **tier-coloured top strip** on agent cards (4px high, full
tier-colour → transparent fade), which gives each tier a quick
visual identifier.

### Borders & shadows (pixel-style)

- Default border: `2px solid var(--bg-0)` — thick, sharp, the
  same near-black `#0b0d14` outline everywhere. Gives the chunky
  16-bit silhouette.
- **Pixel shadows** are hard-offset, **no blur**:
  - `--px-shadow-1` — 2px offset, basic depth.
  - `--px-shadow-2` — 2+4px stacked, default card.
  - `--px-shadow-3` — 4+8px stacked, for modals.
- **Inset highlights** simulate engraved/raised pixel art:
  - `--px-inset-up` — top edge lightened, bottom darkened (raised).
  - `--px-inset-down` — inverted (pressed button).
- **Glow halos** for selected/alerting states: `--glow-blue`,
  `--glow-cyan`, `--glow-ok`, `--glow-warn`, `--glow-dngr`. Each
  is a 2px coloured border + 16–18px coloured halo. Use sparingly
  — at most one element glowing on a screen at a time. The cyan
  glow is reserved for "now" / live-time markers.

### Status LEDs (the signature element)

Every agent card carries a 10×10px **square** LED in its top-right.
Pixel art has no circles — squares with coloured glow are the
standard. The LED has two parts: a solid coloured fill + a same-colour
box-shadow glow at 10–12px radius. **Online** LEDs blink via
`steps(2, end)` (no smooth fade); **failed** LEDs blink faster
(0.55s). Other states are static.

| State | Colour | Animation |
|---|---|---|
| online | `--ok` (#1BC5BD) | 1s blink |
| waiting | `--info` (#3699FF) | static |
| degraded | `--warn` (#FFA800) | static |
| failed | `--danger` (#F1416C) | 0.55s rapid blink |
| offline | `--idle` (#7E8299) | static, dimmed, 1px outline |

### Hover, press, focus

- **Hover** on cards: translate `-2px`, no other change. Pixel art
  doesn't fade.
- **Press** (buttons): translate `+2px, +2px` AND swap
  `--px-inset-up` → `--px-inset-down` so the button visually
  depresses. The 2px shadow vanishes underneath. Classic SNES feel.
- **Focus**: 2px ring in `--accent`. No system ring.
- **Active selection** (e.g. agent picked in roster): full
  `--glow-blue` (cyan glow if it's a live-time element).

### Animation

Minimal and stepped. Three durations — `--dur-1` 100ms,
`--dur-2` 200ms, `--dur-3` 320ms. The signature easing is
`--ease-step: steps(2, end)` which staircases motion instead of
smooth-curving — perfect for pixel sprites. No bounces, no springs.

Two ambient animations only:

- **LED blink** (`@keyframes blink-led`) — 1s on / 0.55s on for
  alarm. Used on status LEDs and the terminal caret.
- **Glow pulse** (`@keyframes pulse-glow`) — used sparingly on the
  active selection.

The meter bars also tick (don't slide) when their value changes —
`steps(2, end)` on the `width` transition.

### Layout rules

- Top bar: ~60px, sticky, `--bg-2`, 2px `--bg-0` divider below.
- Sidebar: 240px, `--bg-2`, tier filter list with active state
  in the tier colour.
- Main grid: 2-column with a 360px right rail (live log +
  schedule strip). Collapses to one column under 1200px.
- Roster: 2-column card grid inside the left column; collapses
  to one column under 720px (mobile).
- Everything aligns to a 4px subgrid.

### Transparency & blur

Reserved for **modals and command-palette overlays**: backdrop is
`--bg-0` at 70% with `backdrop-filter: blur(8px) saturate(150%)`.
Never inside chrome — flat panels everywhere else.

### Imagery

The central visual asset is the **pixel sprite** — a 12×12 SVG
operator portrait per agent, rendered at 48px in the agent card
and 56px in the detail dialog. Each sprite is encoded as 12 strings
of 12 characters in `ui_kits/fleet-console/sprites.jsx`, where each
char maps to a palette slot.

**14 unique sprites**, one per agent. They share a 5-color
**hue-shifted cell-shading ramp** per tier (`D` deep shadow, `S`
shadow, `B` base, `H` highlight, `L` bright highlight), but each
agent has a distinct silhouette — a thematic accessory and chest
emblem:

| Agent | Silhouette cue |
|---|---|
| `scraper-dispatcher` | curved headband + mic boom |
| `listing-validator` | antenna ping + cyan scanner eyes |
| `dedupe-sweeper` | broom bristles across the top |
| `dealer-prospector` | wide scout brim |
| `maker-enricher` | alchemist flask spark |
| `maker-site-doctor` | reflective white forehead mirror |
| `scrape-watchdog` | wolf ears |
| `data-quality-auditor` | librarian glasses bridge |
| `price-anomaly-detector` | deerstalker with two peaks |
| `carpapi-deployer` | rocket helmet nose cone |
| `rds-steward` | parted hair + bowtie |
| `aws-cost-sentinel` | guard crest |
| `ci-cd-doctor` | wide hardhat brim |
| `chat-quality-evaluator` | judge cap with band |

### Pixel-art techniques applied

The sprite system follows the standard rules from the
[`pixel-art-professional` skill](https://github.com/willibrandon/pixel-plugin/blob/main/skills/pixel-art-professional/SKILL.md)
in the willibrandon/pixel-plugin repo:

1. **Hue-shifted color ramps.** Each tier ramp shifts hue across
   the value scale — INGEST's deep shadow is indigo (`#0E1A47`,
   pushed cool/saturated), the base is sky blue (`#3699FF`), and
   the bright highlight desaturates toward near-white
   (`#E2F0FF`). No tier ramps are pure-luminance scales.
2. **Consistent light source: top-left.** Every sprite places
   highlight (`H`) and bright-highlight (`L`) pixels at rows 2–3
   columns 2–3, and shadow (`S`) / deep-shadow (`D`) pixels at
   rows 6–8 columns 8–9. Side-by-side, the fleet reads as if a
   single key light from the upper-left lit every operator.
3. **No pillow shading.** Shadows derive from the light direction,
   not from edge proximity. Edges that face the light source
   stay base-coloured or highlighted; only the far edge picks up
   shadow.
4. **Strong silhouette.** Each sprite reads as a solid black
   shape when colours are merged. The 14 silhouettes are
   distinguishable by outline alone.
5. **No anti-aliasing.** 12×12 is below the AA threshold the
   skill recommends (typically 64×64+). Edges stay crisp and
   stepped — `shape-rendering="crispEdges"` on the SVG enforces
   this even at high zoom.
6. **Bayer dither** is used sparingly (the `--bayer-2-50` and
   `--bayer-4-25` tokens in `colors_and_type.css`) for textures
   on large background panels — never inside the sprite art
   itself.

### Sprite animation

Online sprites breathe via the `.sprite-breathe` class — a 2-frame
`@keyframes sprite-breathe` that translates the SVG +/-1px on the
Y axis with **`animation-timing-function: steps(2, end)`**. The
`steps()` timing is critical: smooth `transform` interpolation
would slide the sprite through sub-pixel positions, breaking the
pixel grid. The breathing duration is 1200ms by default; the
`--dur-breathe` CSS var lets per-component overrides shorten it
for "alert" states.

Following the [`pixel-art-animator` skill](https://github.com/willibrandon/pixel-plugin/blob/main/skills/pixel-art-animator/SKILL.md)
idle-animation patterns: 2 frames, slow timing, ping-pong direction
(`steps(2, end)` on a 0→-1px translation simulates this without
needing two separate SVGs).

No other photography or marketing imagery exists (it's internal
tooling). The CarPapi mark itself — `assets/favicon.svg` — is a
blue car silhouette on a navy rounded square; in the dashboard it's
rebuilt as inline pixel SVG to match the rest of the aesthetic.

### Card anatomy (the signature element)

```
████████████████████████████████████████████   ← 4px tier strip
█ ┌────┐  INGEST · DUAL              ●  █   ← LED (pulse if online)
█ │SPRT│  scraper-dispatcher           █      pixel sprite, 56×56
█ └────┘  Walks active dealers, ...    █      callsign + 2-line desc
█ HP  ████████████████████████████░░░░░░░░░░░   96%  █   ← HP — uptime
█ XP  █████████████░░░░░░░░░░░░░░░░░░░░░░░   14/24 █   ← XP — runs today
█████████████████████████████████████████████
█  LAST  │  NEXT  │  CYCLE                  █   ← stat strip
█  04:12 │  23:48 │  18 MIN                 █      pixel font, big
█████████████████████████████████████████████
   `--bg-3` fill, 2px `--bg-0` border, no radius,
   `--px-shadow-2` + `--px-inset-up`. Tier strip top.
```

When `status === 'degraded'` or `'failed'`, the card also picks up
the matching glow halo (`--glow-warn` or `--glow-dngr`) so problem
agents jump out of the roster without colour-coding the entire body.

---

## Iconography

**There is no icon font in this design system.** Pixel art shrugs
off icon libraries — Bootstrap Icons would clash with the bitmap
type, so the dashboard substitutes:

- **Pixel sprites** for agent identity (12×12 SVG, one template
  per tier, see `ui_kits/fleet-console/sprites.jsx`).
- **Unicode shapes** for inline glyphs: `●` `○` `◐` `▶` `◀` `▲`
  `▼` `→` `✕` `⏸` `▣` `┃` `•` `!!`. Always coloured via
  `currentColor` so they pick up the surrounding semantic colour.
  Examples in use: `▶ SUMMON` (button), `⏸ LOCKED` (disabled
  state), `▣ CONFIRM ACTION` (dialog title), `✕ ABORT` (destructive).
- **The brand mark** — `assets/favicon.svg` — is the only SVG
  asset committed. The dashboard inlines a pixel-redrawn version
  of it in the sidebar.
- **Emoji:** Never.

### Substitution note (flagged for the user)

The parent CarPapi web app uses **Bootstrap Icons** loaded from
jsDelivr (`bi-broadcast`, `bi-cpu`, `bi-shop`, etc., see
`web/frontend/index.html`). This pixel-art system intentionally
*doesn't* inherit that — the vector icons would alias badly at small
pixel-font sizes and break the visual cohesion. If you need to
match the parent product's tooling pages (anything outside the
fleet console), pull Bootstrap Icons via the same CDN link.

---

## UI kits

| Kit | What it covers | Path |
|---|---|---|
| `fleet-console` | The Agent Fleet Console — sidebar tier filter, top HUD, 14-agent roster grid with sprite portraits + HP/XP meters, live VT323 activity feed, 24-hour schedule strip, click-to-open agent detail dialog, `/` to open the summon command palette. | `ui_kits/fleet-console/` |

Each kit has its own `README.md`, an interactive `index.html`, and
modular JSX components.

---

## Caveats

- **Fonts:** all five families (Press Start 2P, Silkscreen, VT323,
  Inter, JetBrains Mono) are pulled from Google Fonts as variable
  woff2 files (latin subset only). They render correctly across the
  weights used but are subset-restricted — if you need extended
  Unicode, swap the files.
- **No real production agent dashboard exists yet** — this design
  system is a forward-looking artifact, not a recreation. It's
  faithful to the agent specs in `CarPapi/.claude/agents/` and the
  CarPapi Demo4 palette base, but the dashboard itself is new
  design work, not a screenshot port.
- **Sprite system is per-agent, fully unique** — 14 distinct
  silhouettes built on shared per-tier hue-shifted ramps. If
  you need new agents, add an entry to `SPRITES` in
  `ui_kits/fleet-console/sprites.jsx` and the dataset in
  `agents.js`.
- **Bootstrap Icons NOT bundled** here — the pixel-art aesthetic
  doesn't pair well with the parent web app's vector icon set.
  Flagged above; substitute as needed.
- **Activity feed is faked** with a setInterval over a pool of
  agent-realistic phrases. Wire a SSE/WebSocket to your real
  CloudWatch log group to make it live.
