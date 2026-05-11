/**
 * UI-only mock for the conversational interface.
 *
 * The chat page hits ``respond()`` synchronously and gets back a
 * shape that mirrors what a real backend would return. No fetch,
 * no LLM — just enough realism to design and test the surface.
 * Swap this module out when the chat backend lands.
 */

const CARS = [
  {
    id: "8d4e7b1a-ford-bronco-sport-25",
    year: 2025,
    make: "Ford",
    model: "Bronco Sport",
    trim: "Outer Banks",
    body_style: "SUV",
    mileage: 12_450,
    mileage_unit: "mi",
    price_amount: 38_750,
    currency: "USD",
    drivetrain: "AWD",
    mpg_city: 25,
    mpg_hwy: 28,
    dealer: "Performance Ford",
    region: "NJ",
    listing_url:
      "https://www.performanceforddealer.com/new/Ford/2025-Ford-Bronco-Sport-d367741aac182624a36828a735124a41.htm",
    maker_url: "https://www.ford.com/suvs/bronco-sport/2025/",
  },
  {
    id: "37f08d49-ford-maverick-25",
    year: 2025,
    make: "Ford",
    model: "Maverick",
    trim: "XLT Hybrid",
    body_style: "Pickup",
    mileage: 8_900,
    mileage_unit: "mi",
    price_amount: 31_995,
    currency: "USD",
    drivetrain: "FWD",
    mpg_city: 42,
    mpg_hwy: 33,
    dealer: "Performance Ford",
    region: "NJ",
    listing_url:
      "https://www.performanceforddealer.com/new/Ford/2025-Ford-Maverick-XLT.htm",
    maker_url: "https://www.ford.com/trucks/maverick/2025/",
  },
  {
    id: "a124-mustang-25",
    year: 2025,
    make: "Ford",
    model: "Mustang",
    trim: "GT Premium",
    body_style: "Coupe",
    mileage: 4_200,
    mileage_unit: "mi",
    price_amount: 54_900,
    currency: "USD",
    drivetrain: "RWD",
    mpg_city: 14,
    mpg_hwy: 22,
    dealer: "Performance Ford",
    region: "NJ",
    listing_url:
      "https://www.performanceforddealer.com/new/Ford/2025-Ford-Mustang-GT.htm",
    maker_url: "https://www.ford.com/cars/mustang/2025/",
  },
  {
    id: "b551-camry-26",
    year: 2026,
    make: "Toyota",
    model: "Camry",
    trim: "SE Hybrid",
    body_style: "Sedan",
    mileage: 2_100,
    mileage_unit: "mi",
    price_amount: 32_450,
    currency: "USD",
    drivetrain: "FWD",
    mpg_city: 51,
    mpg_hwy: 53,
    dealer: "DCH Toyota",
    region: "NJ",
    listing_url: "https://www.dchtoyota.com/new/Toyota/2026-Toyota-Camry-SE.htm",
    maker_url: "https://www.toyota.com/camry/2026/",
  },
  {
    id: "c7a3-corolla-26",
    year: 2026,
    make: "Toyota",
    model: "Corolla",
    trim: "LE",
    body_style: "Sedan",
    mileage: 950,
    mileage_unit: "mi",
    price_amount: 23_800,
    currency: "USD",
    drivetrain: "FWD",
    mpg_city: 32,
    mpg_hwy: 41,
    dealer: "DCH Toyota",
    region: "NJ",
    listing_url:
      "https://www.dchtoyota.com/new/Toyota/2026-Toyota-Corolla-LE.htm",
    maker_url: "https://www.toyota.com/corolla/2026/",
  },
  {
    id: "d8f1-civic-25",
    year: 2025,
    make: "Honda",
    model: "Civic",
    trim: "Sport Touring Hybrid",
    body_style: "Hatchback",
    mileage: 6_300,
    mileage_unit: "mi",
    price_amount: 30_995,
    currency: "USD",
    drivetrain: "FWD",
    mpg_city: 50,
    mpg_hwy: 47,
    dealer: "Open Road Honda",
    region: "NJ",
    listing_url:
      "https://www.openroadhonda.com/new/Honda/2025-Honda-Civic-Sport-Touring.htm",
    maker_url: "https://automobiles.honda.com/civic",
  },
  {
    id: "e2c9-crv-26",
    year: 2026,
    make: "Honda",
    model: "CR-V",
    trim: "EX-L AWD",
    body_style: "SUV",
    mileage: 1_400,
    mileage_unit: "mi",
    price_amount: 36_750,
    currency: "USD",
    drivetrain: "AWD",
    mpg_city: 28,
    mpg_hwy: 34,
    dealer: "Open Road Honda",
    region: "NJ",
    listing_url:
      "https://www.openroadhonda.com/new/Honda/2026-Honda-CR-V-EX-L.htm",
    maker_url: "https://automobiles.honda.com/cr-v",
  },
  {
    id: "f493-mache-25",
    year: 2025,
    make: "Ford",
    model: "Mustang Mach-E",
    trim: "Premium eAWD",
    body_style: "SUV",
    mileage: 5_870,
    mileage_unit: "mi",
    price_amount: 53_230,
    currency: "USD",
    drivetrain: "AWD",
    mpg_city: 110,
    mpg_hwy: 98,
    dealer: "Performance Ford",
    region: "NJ",
    listing_url:
      "https://www.performanceforddealer.com/new/Ford/2025-Ford-Mustang-Mach-E.htm",
    maker_url: "https://www.ford.com/suvs/mustang-mach-e/2025/",
  },
  {
    id: "fa12-silverado-25",
    year: 2025,
    make: "Chevrolet",
    model: "Silverado 1500",
    trim: "LT Trail Boss",
    body_style: "Pickup",
    mileage: 9_800,
    mileage_unit: "mi",
    price_amount: 52_400,
    currency: "USD",
    drivetrain: "4WD",
    mpg_city: 17,
    mpg_hwy: 21,
    dealer: "Multi Chevrolet",
    region: "NJ",
    listing_url:
      "https://www.multichevy.com/new/Chevrolet/2025-Chevrolet-Silverado-1500.htm",
    maker_url: "https://www.chevrolet.com/trucks/silverado-1500/2025/",
  },
  {
    id: "ab23-wrangler-25",
    year: 2025,
    make: "Jeep",
    model: "Wrangler",
    trim: "Sahara 4xe",
    body_style: "SUV",
    mileage: 3_600,
    mileage_unit: "mi",
    price_amount: 58_900,
    currency: "USD",
    drivetrain: "4WD",
    mpg_city: 49,
    mpg_hwy: 49,
    dealer: "Liberty Jeep",
    region: "NJ",
    listing_url:
      "https://www.libertyjeep.com/new/Jeep/2025-Jeep-Wrangler-Sahara-4xe.htm",
    maker_url: "https://www.jeep.com/wrangler-4xe.html",
  },
  {
    id: "cd34-rav4-26",
    year: 2026,
    make: "Toyota",
    model: "RAV4",
    trim: "XLE Hybrid",
    body_style: "SUV",
    mileage: 1_120,
    mileage_unit: "mi",
    price_amount: 36_400,
    currency: "USD",
    drivetrain: "AWD",
    mpg_city: 41,
    mpg_hwy: 38,
    dealer: "DCH Toyota",
    region: "NJ",
    listing_url:
      "https://www.dchtoyota.com/new/Toyota/2026-Toyota-RAV4-XLE.htm",
    maker_url: "https://www.toyota.com/rav4/2026/",
  },
  {
    id: "ef45-tahoe-24",
    year: 2024,
    make: "Chevrolet",
    model: "Tahoe",
    trim: "LS",
    body_style: "SUV",
    mileage: 22_300,
    mileage_unit: "mi",
    price_amount: 49_995,
    currency: "USD",
    drivetrain: "4WD",
    mpg_city: 14,
    mpg_hwy: 19,
    dealer: "Multi Chevrolet",
    region: "NJ",
    listing_url:
      "https://www.multichevy.com/used/Chevrolet/2024-Chevrolet-Tahoe-LS.htm",
    maker_url: "https://www.chevrolet.com/suvs/tahoe/2024/",
  },
];

const HEDGES = [
  "Here's what's on the lot right now.",
  "I pulled a few matches from active dealer inventory:",
  "Three picks that line up with what you described:",
  "Best fits from current listings:",
  "These are live — feel free to tap through to the dealer page.",
];

function parseFilters(text) {
  const t = (text || "").toLowerCase();
  const filters = {};

  // Make
  for (const make of [
    "ford", "toyota", "honda", "chevrolet", "chevy",
    "jeep", "ram", "gmc", "bmw", "audi", "tesla",
  ]) {
    if (t.includes(make)) {
      filters.make = make === "chevy" ? "chevrolet" : make;
      break;
    }
  }

  // Body style
  for (const [needle, value] of [
    ["truck", "Pickup"], ["pickup", "Pickup"],
    ["suv", "SUV"], ["crossover", "SUV"],
    ["sedan", "Sedan"],
    ["coupe", "Coupe"],
    ["hatchback", "Hatchback"],
  ]) {
    if (t.includes(needle)) {
      filters.body_style = value;
      break;
    }
  }

  // Drivetrain
  if (/\b(awd|all[\s-]?wheel)\b/.test(t)) filters.drivetrain = "AWD";
  else if (/\b4wd\b|\b4x4\b|four[\s-]?wheel/.test(t)) filters.drivetrain = "4WD";

  // Fuel-economy / hybrid / electric
  if (t.includes("hybrid")) filters.tag = "hybrid";
  if (t.includes("electric") || t.includes(" ev ") || t.endsWith(" ev")) {
    filters.tag = "electric";
  }

  // Price ceiling — $35k, under 40000, less than 30k
  let m = t.match(/(?:under|less than|below|<=?|max|≤)\s*\$?\s*([\d,]+)\s*(k)?/);
  if (m) {
    let n = parseInt(m[1].replace(/,/g, ""), 10);
    if (m[2] === "k" || n < 1000) n *= 1000;
    if (n > 0) filters.price_max = n;
  }
  // $XXk plain
  m = t.match(/\$\s*([\d,]+)\s*k\b/);
  if (m && !filters.price_max) {
    filters.price_max = parseInt(m[1].replace(/,/g, ""), 10) * 1000;
  }

  // Year minimum — "2024+" or "2024 or newer"
  m = t.match(/(20\d{2})\s*(?:\+|or newer|and newer|or later)/);
  if (m) filters.year_min = parseInt(m[1], 10);
  // Specific year
  m = t.match(/\b(20\d{2})\b/);
  if (m && !filters.year_min) filters.year_min = parseInt(m[1], 10);

  return filters;
}

function rank(cars, filters) {
  return cars
    .map((c) => {
      let score = 0;
      if (filters.make && c.make.toLowerCase() === filters.make) score += 5;
      if (filters.body_style && c.body_style === filters.body_style) score += 4;
      if (filters.drivetrain && c.drivetrain === filters.drivetrain) score += 2;
      if (filters.tag === "hybrid" && /hybrid/i.test(c.trim)) score += 4;
      if (filters.tag === "electric" && /mach-e|ev|lightning/i.test(c.model)) score += 4;
      if (filters.year_min && c.year >= filters.year_min) score += 1;
      if (filters.price_max && c.price_amount <= filters.price_max) score += 2;
      if (filters.price_max && c.price_amount > filters.price_max) score -= 6;
      return { car: c, score };
    })
    .filter((s) => s.score > -3)
    .sort((a, b) => b.score - a.score);
}

function buildPreface(filters, results) {
  if (results.length === 0) {
    return "I didn't find a tight match in current inventory — try widening the price or year range.";
  }
  const bits = [];
  if (filters.make) bits.push(filters.make[0].toUpperCase() + filters.make.slice(1));
  if (filters.body_style) bits.push(filters.body_style.toLowerCase());
  if (filters.tag === "hybrid") bits.unshift("hybrid");
  if (filters.tag === "electric") bits.unshift("electric");
  if (filters.drivetrain) bits.push(`with ${filters.drivetrain}`);
  if (filters.price_max) bits.push(`under $${filters.price_max.toLocaleString()}`);

  const subject = bits.length ? bits.join(" ") : "matching listings";
  const n = results.length;
  const hedge = HEDGES[Math.floor(Math.random() * HEDGES.length)];
  return `I found ${n} ${subject}${n === 1 ? "" : ""}. ${hedge}`;
}

/**
 * Public API: respond(prompt) → { text, results, filters }.
 *
 * Drop-in replacement: a real backend would return the same shape.
 */
export function respond(prompt) {
  const filters = parseFilters(prompt);
  const ranked = rank(CARS, filters);
  const results = ranked.slice(0, ranked.length === 0 ? 0 : Math.min(4, ranked.length)).map((r) => r.car);
  const text = buildPreface(filters, results);
  return { text, results, filters };
}

export const SAMPLE_PROMPTS = [
  "Find me a Ford truck under $35k",
  "Hybrid sedan 2024 or newer",
  "Toyota SUV with AWD",
  "Electric car near NJ",
  "Best Jeep Wrangler available right now",
];

export default { respond, SAMPLE_PROMPTS };
