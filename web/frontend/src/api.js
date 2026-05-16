// API client.
//
// Auth model (JWT Bearer):
//   1. Login or register → backend returns { access, refresh, user }
//   2. We persist all three to localStorage under
//      carpapi.auth.v2 (single JSON blob; easier than 3 keys to
//      keep in sync across tabs).
//   3. Every API call sends `Authorization: Bearer <access>`.
//   4. 401 from any call → clear the saved auth + throw
//      AuthRequiredError so the caller can bounce to /login.
//
// VITE_API_BASE — same behaviour as before. Default "/api" (relative)
// works in dev + when the API is same-origin. Absolute URL points at
// App Runner in production.
const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const IS_ABSOLUTE = /^https?:\/\//i.test(API_BASE);

export const AUTH_STORAGE_KEY = "carpapi.auth.v2";

export class AuthRequiredError extends Error {
  constructor(message = "auth required") {
    super(message);
    this.name = "AuthRequiredError";
  }
}

// ──────────────────────────────────────────────────────────────────── //
// Auth state in localStorage
// ──────────────────────────────────────────────────────────────────── //

export function getAuth() {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setAuth(auth) {
  if (typeof window === "undefined") return;
  try {
    if (auth) localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
    else localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    /* ignore quota */
  }
}

function authHeaders() {
  const a = getAuth();
  return a && a.access ? { Authorization: `Bearer ${a.access}` } : {};
}

// ──────────────────────────────────────────────────────────────────── //
// URL helpers
// ──────────────────────────────────────────────────────────────────── //

function buildUrl(path, params) {
  const cleanPath = path.startsWith("/") ? path : "/" + path;
  const base = API_BASE.replace(/\/$/, "");
  const origin = IS_ABSOLUTE ? "" : window.location.origin;
  const url = new URL(base + cleanPath, origin || undefined);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  return url;
}

/** Absolute backend origin — used for OAuth redirects to /accounts/...
 *  Those endpoints live outside /api/ so we strip the /api suffix. */
export function backendOrigin() {
  if (IS_ABSOLUTE) {
    return API_BASE.replace(/\/api\/?$/, "");
  }
  return window.location.origin;
}

// ──────────────────────────────────────────────────────────────────── //
// Low-level HTTP
// ──────────────────────────────────────────────────────────────────── //

async function httpJson(method, path, body, opts) {
  const url = buildUrl(path);
  const init = {
    method,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...(opts && opts.headers ? opts.headers : {}),
    },
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  const res = await fetch(url.toString(), init);

  // Try to surface JSON error bodies even on non-2xx.
  let payload = null;
  const ct = res.headers.get("Content-Type") || "";
  if (ct.includes("application/json")) {
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
  }

  if (res.status === 401) {
    setAuth(null);
    const err = new AuthRequiredError(
      (payload && (payload.detail || payload.error)) || "auth required",
    );
    err.payload = payload;
    throw err;
  }
  if (!res.ok) {
    const err = new Error(
      (payload && (payload.detail || payload.error)) ||
        `${res.status} ${res.statusText}`,
    );
    err.status = res.status;
    err.payload = payload;
    throw err;
  }
  return payload;
}

export async function getJson(path, params = {}) {
  const url = buildUrl(path, params);
  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json", ...authHeaders() },
  });
  if (res.status === 401) {
    setAuth(null);
    throw new AuthRequiredError();
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

export async function postJson(path, body) {
  return httpJson("POST", path, body);
}

// ──────────────────────────────────────────────────────────────────── //
// Auth API
// ──────────────────────────────────────────────────────────────────── //

/** Email + password login. Returns the full auth blob.
 *
 * Clears any locally-saved auth FIRST so a stale JWT doesn't ride
 * along on the login request itself — SimpleJWT rejects requests
 * with bad Bearer tokens before the view runs, which would cause
 * a freshly-attempted sign-in to fail with "Given token not valid
 * for any token type".
 */
export async function login({ email, password }) {
  setAuth(null);
  const res = await httpJson("POST", "/auth/login/", { email, password });
  // dj-rest-auth response shape: { access, refresh, user }
  const auth = { access: res.access, refresh: res.refresh, user: res.user };
  setAuth(auth);
  return auth;
}

/** Email/password registration. Returns the full auth blob.
 *
 * Same defensive clear as login() — a stale JWT in localStorage
 * would cause the registration request to 401 before reaching
 * the view.
 */
export async function register({
  email,
  password,
  full_name,
  phone,
  marketing_opt_in,
}) {
  setAuth(null);
  const res = await httpJson("POST", "/auth/registration/", {
    email,
    password1: password,
    password2: password,
    full_name: full_name || "",
    phone: phone || null,
    marketing_opt_in: !!marketing_opt_in,
  });
  const auth = { access: res.access, refresh: res.refresh, user: res.user };
  setAuth(auth);
  return auth;
}

/** Logs the user out client-side. Backend logout is best-effort. */
export async function logout() {
  try {
    await httpJson("POST", "/auth/logout/", {});
  } catch {
    /* server may have already invalidated; we wipe locally regardless */
  }
  setAuth(null);
}

/** Reads the saved user (cached) or null. */
export function currentUser() {
  const a = getAuth();
  return a ? a.user : null;
}

// ─────────────────────────────────────────────────────────────────────
// Notification preferences (backed by notifications/views.py)
// ─────────────────────────────────────────────────────────────────────

/** GET /api/notifications/preferences/ — returns
 *  `{ categories: [{key,label,enabled}], cc_email, updated_at }`. */
export async function getNotificationPreferences() {
  return httpJson("GET", "/notifications/preferences/");
}

/** PATCH /api/notifications/preferences/.
 *  `categories` is { key: bool, ... }. `cc_email` is a string or "".
 *  Returns the updated payload (same shape as the GET). */
export async function updateNotificationPreferences({ categories, cc_email }) {
  const body = {};
  if (categories) body.categories = categories;
  if (cc_email !== undefined) body.cc_email = cc_email;
  return httpJson("PATCH", "/notifications/preferences/", body);
}

/** POST /api/notifications/test/ — fires a sandbox-safe test email to
 *  the logged-in user's address. Returns
 *  `{ ok, status, ses_message_id, error, to, from }`. */
export async function sendTestNotification() {
  return httpJson("POST", "/notifications/test/", {});
}

// ─────────────────────────────────────────────────────────────────────
// Autonomous-agent fleet (backed by web/backend/api/views_agents.py)
// ─────────────────────────────────────────────────────────────────────

/** GET /api/agents/ — returns
 *   { agents: [{slug, tier, type, cadence, desc, deployed, lambda,
 *               schedule, metrics_24h, last_event, status}],
 *     summary: {total, online, idle, ..., invocations_24h, errors_24h},
 *     as_of_utc: "..." }
 *  Each agent's status is one of: online | idle | degraded | failed |
 *  not_deployed.  */
export async function getAgents() {
  return getJson("/agents/");
}

/** POST /api/agents/<slug>/run/ — queue a manual run for an agent.
 *
 *  Returns the marker payload from the backend (queue_key,
 *  lambda_name, requested_at_ms, expected_invoke_within_s).
 *  Throws on non-2xx — caller surfaces error.body.error to the user.
 */
export async function runAgent(slug, { reason, payload } = {}) {
  return postJson(`/agents/${encodeURIComponent(slug)}/run/`, {
    reason, payload,
  });
}

/** URL the Sign-In-With-Google button links to. App Runner handles
 *  the OAuth dance via allauth, then bounces back to `next`. */
export function googleLoginUrl(next) {
  const origin = backendOrigin();
  const nextAbs = next.startsWith("http")
    ? next
    : window.location.origin + next;
  return `${origin}/accounts/google/login/?next=${encodeURIComponent(nextAbs)}`;
}

// ──────────────────────────────────────────────────────────────────── //
// Shape adapter — backend /api/chat/ → Chat.jsx CarCard
// ──────────────────────────────────────────────────────────────────── //

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
    // Image pipeline output — see carpapi/images/ + .claude/agents/image-pipeline.md
    image_url: l.image_url || null,
    image_svg_url: l.image_svg_url || null,
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
