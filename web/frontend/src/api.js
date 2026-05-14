// API client.
//
// VITE_API_BASE behaviour:
//   - default ("/api")          : relative; works in dev (vite proxy) +
//                                 any setup where the API is same-origin
//                                 with the static site.
//   - absolute (https://...)    : production cloud deploys where the API
//                                 lives on a separate host (App Runner).
//                                 The fetch goes cross-origin; the Django
//                                 side needs CORS to allow our origin.
//
// Auth model (shared passphrase, not user accounts):
//   - getApiToken() returns the token saved by the Login page.
//   - It's sent as `X-CarPapi-Auth: <token>` on every request.
//   - The Django side validates the header against env CARPAPI_API_KEY.
//   - 401 from any call triggers a redirect back to /login via the
//     thrown AuthRequiredError instance.
const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const IS_ABSOLUTE = /^https?:\/\//i.test(API_BASE);

export const AUTH_STORAGE_KEY = "carpapi.auth.token.v1";

export class AuthRequiredError extends Error {
  constructor(message = "auth required") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

export function getApiToken() {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(AUTH_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function setApiToken(token) {
  if (typeof window === "undefined") return;
  try {
    if (token) localStorage.setItem(AUTH_STORAGE_KEY, token);
    else localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    /* ignore quota */
  }
}

function buildUrl(path, params) {
  const cleanPath = path.startsWith("/") ? path : "/" + path;
  const base = IS_ABSOLUTE
    ? API_BASE.replace(/\/$/, "")
    : API_BASE.replace(/\/$/, "");
  const baseOrigin = IS_ABSOLUTE ? "" : window.location.origin;
  const url = new URL(base + cleanPath, baseOrigin || undefined);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  return url;
}

function authHeaders() {
  const t = getApiToken();
  return t ? { "X-CarPapi-Auth": t } : {};
}

export async function getJson(path, params = {}) {
  const url = buildUrl(path, params);
  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json", ...authHeaders() },
  });
  if (res.status === 401) throw new AuthRequiredError();
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return res.json();
}

export async function postJson(path, body) {
  const url = buildUrl(path);
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (res.status === 401) throw new AuthRequiredError();
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return res.json();
}

// --------------------------------------------------------------------- //
// Shape adapter — backend /api/chat/ → Chat.jsx CarCard
// --------------------------------------------------------------------- //
//
// The backend returns `listings` with fields:
//   { id, vin, title, make, model, year, trim, body_style,
//     mileage, price, currency, city, region, url, dealer, similarity }
// The frontend CarCard expects:
//   { id, year, make, model, trim, body_style, mileage, mileage_unit,
//     price_amount, currency, drivetrain, mpg_city, mpg_hwy, dealer,
//     listing_url, maker_url }
//
// We translate at the API boundary so Chat.jsx stays clean.
export function adaptListing(l) {
  return {
    id: l.id,
    year: l.year,
    make: l.make,
    model: l.model,
    trim: l.trim,
    body_style: l.body_style,
    mileage: l.mileage,
    mileage_unit: "mi",
    price_amount: l.price,
    currency: l.currency || "USD",
    drivetrain: null,
    mpg_city: null,
    mpg_hwy: null,
    dealer: l.dealer,
    region: l.region,
    listing_url: l.url,
    maker_url: null,
  };
}

export async function chat(message) {
  const res = await postJson("/chat/", { message });
  return {
    text: res.answer,
    results: (res.listings || []).map(adaptListing),
    rationale: res.rationale,
    diagnostics: res.diagnostics,
  };
}
