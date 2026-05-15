---
name: carpapi-fleet-design
description: Use this skill to generate well-branded interfaces and assets for the CarPapi Fleet — the operational AI-agent management dashboard. The aesthetic is 16-bit JRPG party-screen / arcade command-center, built on top of the CarPapi "Demo4" palette (#1e1e2d navy, #3699FF blue). Use for production code, throwaway prototypes, slides, mocks, anything that should look like the CarPapi agent fleet UI. Includes design tokens, pixel + terminal fonts, agent sprite system, and ready-made dashboard components.
user-invocable: true
---

# CarPapi Fleet — Design Skill

Read the **`README.md`** at the root of this skill first — it has
the full visual and content foundations (palette, type, animation,
card anatomy, iconography, voice).

## Where things live

```
README.md                       Full system docs
colors_and_type.css             All design tokens (CSS variables) + @font-face
fonts/                          Self-hosted Inter, JBM, Press Start 2P, Silkscreen, VT323
assets/                         Brand mark (favicon.svg)
preview/                        Per-token preview cards (load any .html in a browser)
ui_kits/fleet-console/          The full Agent Fleet Console kit
  ├── index.html                Entry point (React + Babel inline)
  ├── agents.js                 14-agent dataset + tier list + log pool
  ├── sprites.jsx               <Sprite> + 5 tier sprite templates (12×12)
  └── components.jsx            <AgentCard>, <Sidebar>, <Header>, <LogFeed>,
                                <ScheduleStrip>, <AgentDialog>, <SummonPalette>,
                                <MeterBar>, <StatusLED>, <TierChip>
```

## How to use

### If you are making a visual artifact (slide, mock, prototype)

1. Copy `colors_and_type.css` and the `fonts/` folder into your
   output folder.
2. Link the CSS from your HTML: `<link rel="stylesheet" href="colors_and_type.css">`.
3. Pick a type scale from the token table at the top of the CSS file
   (`--t-title`, `--t-h2`, `--t-callsign`, `--t-body`, etc.) — don't
   freestyle font sizes.
4. Surfaces: stack `var(--scanlines)` + `var(--vignette)` over
   `var(--bg-1)` on the body. Cards live on `var(--bg-3)` with a
   2px `var(--bg-0)` border and `var(--px-shadow-2)`.
5. If you need agent cards or the roster grid, lift the JSX
   components from `ui_kits/fleet-console/components.jsx` — they
   already use the right tokens.

### If you are writing production code for the CarPapi fleet UI

1. The tokens are stable — import `colors_and_type.css` directly.
2. The components in `ui_kits/fleet-console/` are visual prototypes,
   not production code (they use inline styles, no build step,
   demo data). Treat them as a reference implementation. The
   parent CarPapi web app uses Vite + React 18 + Bootstrap 5 — see
   `CarPapi/web/frontend/` for the real build setup.
3. The 14-agent dataset in `agents.js` mirrors the specs in
   `CarPapi/.claude/agents/*.md`. Source of truth for any agent
   behaviour change is the markdown spec, not the dashboard.

### If the user invokes this skill without other guidance

Ask them what they're building:

- A new screen in the fleet console? Ask which view (roster /
  detail / log / schedule / summon) and what data lives there.
- A slide / one-pager about the fleet? Ask the audience (engineers
  / leadership / external) — the pixel aesthetic is fun for
  engineers but might be off-tone for an investor deck.
- A throwaway mock? Pull a screen from the fleet console and tweak.
- Something outside the fleet (a marketing page, the chat UI, etc.)?
  This skill is **not** the right fit — point them at the parent
  CarPapi web app's `theme.css` Demo4 system, which is the
  production design language for the rest of the product.

Always check the README for voice / tone before writing copy. The
fleet voice is **deadpan-technical**, sentence-case, no emoji,
short. Never let the pixel-art shell trick you into cute copy.

## Source repos

- `ceylanbagci/carpapi` (GitHub) — the CarPapi codebase the agents
  manage. Explore for richer context.
