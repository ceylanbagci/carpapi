/*
 * Pixel sprite system v2 — applies pixel-art-professional principles:
 *
 *  1. **Cell shading** with 5-color hue-shifted ramps per tier
 *     (deep / shadow / base / highlight / bright). No flat fills,
 *     no luminance-only ramps.
 *  2. **Light source from top-left** consistently — every sprite
 *     places highlight on rows 2-3 / cols 2-3 and shadow on rows
 *     6-8 / cols 8-9.
 *  3. **No pillow shading** — shadows come from light direction,
 *     never as a ring around the silhouette.
 *  4. **Strong silhouette** — every sprite reads as solid black
 *     when shapes are merged (verified by eye).
 *  5. **Per-agent accessory + emblem** — the head silhouette
 *     varies by agent (headset, antenna, brim, ears, hat),
 *     plus a 2-3 pixel chest emblem.
 *  6. **Stepped breathing animation** — applied via the
 *     `.sprite-breathe` CSS class with `steps(2, end)` so the
 *     bob jumps a single pixel, never interpolates.
 *
 * Grid: 12×12. Char codes:
 *   .  transparent
 *   #  outline (#0b0d14)
 *   D  deep shadow      (--tier-X-d)
 *   S  shadow           (--tier-X-s)
 *   B  base             (--tier-X)
 *   H  highlight        (--tier-X-h)
 *   L  bright highlight (--tier-X-b)
 *   e  eye              (#0b0d14)
 *   w  white            (#ffffff)
 *   k  pure black (chest emblem / mouth)
 *   y  amber accent (#ffa800)
 *   c  cyan accent (#5eead4)
 *   r  pink/danger      (#f472b6)
 *   g  green/ok         (#1bc5bd)
 */

const TIER_RAMPS = {
  ingest:   { D: "#0E1A47", S: "#1F5FC4", B: "#3699FF", H: "#93C4FF", L: "#E2F0FF" },
  enrich:   { D: "#261758", S: "#6E4EC4", B: "#B794F6", H: "#DCC4FB", L: "#F5EDFF" },
  quality:  { D: "#0E3A36", S: "#2C8A7D", B: "#5EEAD4", H: "#A8F0E0", L: "#E8FDF6" },
  cloud:    { D: "#4A2400", S: "#B07300", B: "#FFA800", H: "#FFCE6E", L: "#FFF2D0" },
  delivery: { D: "#4A1242", S: "#B03A83", B: "#F472B6", H: "#FBB4D6", L: "#FCE8F3" },
};
const ACCENTS = { "#": "#0b0d14", e: "#0b0d14", k: "#000000", w: "#ffffff",
                  y: "#FFA800", c: "#5EEAD4", r: "#F472B6", g: "#1BC5BD" };

/* ---------- 14 unique sprites ----------
 * Each is exactly 12 strings of 12 chars. Light source: top-left.
 * Tier sets the palette; the silhouette and emblem vary per agent.
 */
const SPRITES = {
  // ---------- INGEST ----------
  /* SD scraper-dispatcher — headset operator. Curved headband on top,
     mic boom extending right of the jaw. */
  "scraper-dispatcher": {
    tier: "ingest",
    grid: [
      "............",
      "...######...",   // headband top
      "..#HHBBBBS#.",   // headband front, TL highlight
      ".#HBBSSBBSS#",   // forehead
      ".#HBeeBBeeS#",   // eyes
      ".#BBBBBBBBS#",   // mid-face
      ".#HSBBkBBSS#",   // mouth + cheek shadow
      ".#BSSSSSSSB#",   // jaw shadow strip
      "..#SSBBSS#cc",   // mic boom extends right
      "...######...",
      "....####....",   // comms collar
      "....#BB#....",
    ],
  },
  /* LV listing-validator — cyan-eyed scanner; thin antenna with ping. */
  "listing-validator": {
    tier: "ingest",
    grid: [
      ".....cc.....",   // antenna ping (cyan)
      ".....##.....",   // antenna stem
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBccBBccS#",   // cyan scan-eyes
      ".#BBeeBBeeB#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",   // wider mouth grill
      "..########..",
      "............",
      "....####....",
      "....#cc#....",   // scanner emblem
    ],
  },
  /* DS dedupe-sweeper — bristle row on top (broom). */
  "dedupe-sweeper": {
    tier: "ingest",
    grid: [
      "#.#.#.#.#.#.",   // bristle tips
      "############",   // broom backstrip
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBBBBSS#",
      "..########..",
      "............",
      "............",
      "....####....",
      "....#×=#....".replace("×","B").replace("=","B"),
    ],
  },
  /* DP dealer-prospector — scout brim hat (wider than head). */
  "dealer-prospector": {
    tier: "ingest",
    grid: [
      "............",
      "...######...",   // hat crown
      "############",   // brim
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",   // small mouth
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#yy#....",   // amber compass emblem
    ],
  },

  // ---------- ENRICH ----------
  /* ME maker-enricher — alchemist with flask spark. */
  "maker-enricher": {
    tier: "enrich",
    grid: [
      ".....L......",   // flask spark
      "....###.....",
      "...#HHB#....",   // flask top
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#LL#....",
    ],
  },
  /* MD maker-site-doctor — mirror band across forehead (canary). */
  "maker-site-doctor": {
    tier: "enrich",
    grid: [
      "............",
      "...######...",
      "..#wwwwwwww#",   // reflective mirror band
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#ww#....",
    ],
  },

  // ---------- QUALITY ----------
  /* SW scrape-watchdog — wolf ears poking above. */
  "scrape-watchdog": {
    tier: "quality",
    grid: [
      ".##......##.",   // wolf ears
      ".##......##.",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",   // muzzle
      ".#BSkkkkSSB#",   // teeth strip
      "..########..",
      "............",
      "....####....",
      "....#gg#....",
    ],
  },
  /* DQ data-quality-auditor — wide rectangular glasses. */
  "data-quality-auditor": {
    tier: "quality",
    grid: [
      "............",
      "...######...",
      "..#HBBBBBS#.",
      ".#HBBBBBSSS#",
      ".########B#.",   // glasses bridge (full row of outlines across eye row)
      ".#BeeBBeeBS#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#cc#....",
    ],
  },
  /* PA price-anomaly-detector — deerstalker (front+back peaks). */
  "price-anomaly-detector": {
    tier: "quality",
    grid: [
      "..#......#..",   // peaks
      ".####..####.",
      "############",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#yr#....",   // mixed badge
    ],
  },

  // ---------- CLOUD-OPS ----------
  /* CD carpapi-deployer — rocket helmet dome. */
  "carpapi-deployer": {
    tier: "cloud",
    grid: [
      "....##......",   // nose cone
      "...####.....",
      "..########..",
      ".#HBBBBBBS#.",   // visor with reflective sheen
      ".#HLLLLLBS#.",
      ".#BeeBBeeBS#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#yy#....",
    ],
  },
  /* RS rds-steward — slick parted hair on top. */
  "rds-steward": {
    tier: "cloud",
    grid: [
      "............",
      "..##.####...",   // parted hair
      "..##########",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "...######...",
      "...#wHHw#...",   // bowtie
    ],
  },
  /* CS aws-cost-sentinel — guard helmet crest. */
  "aws-cost-sentinel": {
    tier: "cloud",
    grid: [
      "....##......",   // crest
      "....##......",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#yy#....",   // $ badge
    ],
  },

  // ---------- DELIVERY ----------
  /* CI ci-cd-doctor — hardhat (wide brim with reinforcement strip). */
  "ci-cd-doctor": {
    tier: "delivery",
    grid: [
      "............",
      "...######...",   // hat dome
      "############",   // brim
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#yy#....",
    ],
  },
  /* CQ chat-quality-evaluator — judge cap with tassel. */
  "chat-quality-evaluator": {
    tier: "delivery",
    grid: [
      "............",
      "..########..",   // cap top
      ".#HBBBBBBSS#",
      "############",   // cap band
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "....####....",
      "....#gr#....",
    ],
  },
};

function colorAt(ch, tier) {
  if (ch === "." || ch === " ") return null;
  if (ACCENTS[ch] !== undefined) return ACCENTS[ch];
  const ramp = TIER_RAMPS[tier];
  if (ramp && ramp[ch]) return ramp[ch];
  return null;
}

/* Renders any 12×12 sprite via SVG <rect>s. shape-rendering=crispEdges
   keeps pixels sharp at any zoom. */
function Sprite({ agentId, tier, size = 48, breathe = false }) {
  const spec = SPRITES[agentId];
  const t = spec?.tier || tier || "ingest";
  // fallback: if agentId is unknown, default to ingest dispatcher silhouette
  const grid = spec?.grid || SPRITES["scraper-dispatcher"].grid;
  const w = 12, h = 12;

  return (
    <svg
      width={size} height={size}
      viewBox={`0 0 ${w} ${h}`}
      shapeRendering="crispEdges"
      className={breathe ? "sprite-breathe" : ""}
      style={{ display: "block", imageRendering: "pixelated" }}
    >
      {grid.flatMap((row, y) =>
        [...row].map((ch, x) => {
          const fill = colorAt(ch, t);
          if (!fill) return null;
          return <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" fill={fill} />;
        })
      )}
    </svg>
  );
}

Object.assign(window, { Sprite, TIER_RAMPS, SPRITES });
