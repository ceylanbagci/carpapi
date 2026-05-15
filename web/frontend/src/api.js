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
