import React from "react";

/*
 * Pixel sprite system — ported from
 * CarPapi Fleet _ Design System/ui_kits/fleet-console/sprites.jsx.
 *
 * 12×12 grid. Char codes:
 *   .  transparent
 *   #  outline (#0b0d14)
 *   D/S/B/H/L  tier-color ramp (deep / shadow / base / highlight / bright)
 *   e  eye  (#0b0d14)   w  white   k  black   y  amber
 *   c  cyan  r  pink    g  green
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

const SPRITES = {
  // ---------- INGEST ----------
  "scraper-dispatcher": {
    tier: "ingest",
    grid: [
      "............",
      "...######...",
      "..#HHBBBBS#.",
      ".#HBBSSBBSS#",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..#SSBBSS#cc",
      "...######...",
      "....####....",
      "....#BB#....",
    ],
  },
  "listing-validator": {
    tier: "ingest",
    grid: [
      ".....cc.....",
      ".....##.....",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBccBBccS#",
      ".#BBeeBBeeB#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#cc#....",
    ],
  },
  "dedupe-sweeper": {
    tier: "ingest",
    grid: [
      "#.#.#.#.#.#.",
      "############",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBBBBSS#",
      "..########..",
      "............",
      "............",
      "....####....",
      "....#BB#....",
    ],
  },
  "dealer-prospector": {
    tier: "ingest",
    grid: [
      "............",
      "...######...",
      "############",
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
  /* DZ dealer-zip-scraper — map-pin antenna on top, grid emblem on chest */
  "dealer-zip-scraper": {
    tier: "ingest",
    grid: [
      "....##......",
      "...####.....",
      "....##......",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#cy#....",
    ],
  },

  // ---------- ENRICH ----------
  "maker-enricher": {
    tier: "enrich",
    grid: [
      ".....L......",
      "....###.....",
      "...#HHB#....",
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
  "maker-site-doctor": {
    tier: "enrich",
    grid: [
      "............",
      "...######...",
      "..#wwwwwwww#",
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
  "scrape-watchdog": {
    tier: "quality",
    grid: [
      ".##......##.",
      ".##......##.",
      "..########..",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSkkkkSSB#",
      "..########..",
      "............",
      "....####....",
      "....#gg#....",
    ],
  },
  "data-quality-auditor": {
    tier: "quality",
    grid: [
      "............",
      "...######...",
      "..#HBBBBBS#.",
      ".#HBBBBBSSS#",
      ".########B#.",
      ".#BeeBBeeBS#",
      ".#BBBBBBBBS#",
      ".#HSBkkkBSS#",
      "..########..",
      "............",
      "....####....",
      "....#cc#....",
    ],
  },
  "price-anomaly-detector": {
    tier: "quality",
    grid: [
      "..#......#..",
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
      "....#yr#....",
    ],
  },

  // ---------- CLOUD-OPS ----------
  "carpapi-deployer": {
    tier: "cloud",
    grid: [
      "....##......",
      "...####.....",
      "..########..",
      ".#HBBBBBBS#.",
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
  "rds-steward": {
    tier: "cloud",
    grid: [
      "............",
      "..##.####...",
      "..##########",
      ".#HBBBBBBS#.",
      ".#HBeeBBeeS#",
      ".#BBBBBBBBS#",
      ".#HSBBkBBSS#",
      ".#BSSSSSSSB#",
      "..########..",
      "............",
      "...######...",
      "...#wHHw#...",
    ],
  },
  "aws-cost-sentinel": {
    tier: "cloud",
    grid: [
      "....##......",
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
      "....#yy#....",
    ],
  },

  // ---------- DELIVERY ----------
  "ci-cd-doctor": {
    tier: "delivery",
    grid: [
      "............",
      "...######...",
      "############",
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
  "chat-quality-evaluator": {
    tier: "delivery",
    grid: [
      "............",
      "..########..",
      ".#HBBBBBBSS#",
      "############",
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

export function Sprite({ agentId, tier, size = 48, breathe = false }) {
  const spec = SPRITES[agentId];
  const t = spec?.tier || tier || "ingest";
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

export { TIER_RAMPS, SPRITES };
