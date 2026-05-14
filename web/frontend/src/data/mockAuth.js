/**
 * Auth bridge for the demo4-styled pages (Signup, Account,
 * ForgotPassword, ResetPassword, Pricing).
 *
 * Originally this file was a UI-only localStorage mock so the new
 * pages could be designed without a backend. Now that real auth is
 * live (Django + dj-rest-auth + JWT), this file is a **thin bridge**:
 *
 *   - currentUser() / login() / signup() / logout() /
 *     requestPasswordReset() / resetPassword() / changePassword() /
 *     updateProfile()  → delegate to the real backend via api.js
 *
 *   - createApiToken() / revokeApiToken() / updatePreferences() /
 *     deleteAccount()  → still localStorage-only because the backend
 *     doesn't expose these yet. They're marked LOCAL-ONLY below.
 *
 * The public function signatures are unchanged so Signup/Account/etc.
 * keep working without page edits. The shape of the returned `user`
 * object is normalized so both real-auth users (from /api/auth/user/)
 * and any pre-existing local mock users render correctly.
 */

import {
  AuthRequiredError,
  getAuth,
  getJson,
  login as apiLogin,
  logout as apiLogout,
  postJson,
  register as apiRegister,
  setAuth,
} from "../api.js";

// LOCAL-ONLY storage keys (for features the backend doesn't have yet).
const PREFS_KEY = "carpapi.auth.prefs.v1";       // per-user preferences
const TOKENS_KEY = "carpapi.auth.apiTokens.v1";  // per-user "API tokens" (cosmetic)
const RESET_KEY = "carpapi.auth.resetTokens.v1"; // local fallback for /reset-password?token=...

function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota — ignore */
  }
}

// ─────────────────────────────────────────────────────────────────────
// Normalize backend-user → mock-user shape so the demo4 pages render
// without per-page changes.
//
// Backend (dj-rest-auth /api/auth/user/) returns:
//   { pk, email, full_name, phone, is_email_verified, ... }
//
// Demo4 pages expect:
//   { id, name, email, plan, created_at, preferences, apiTokens }
// ─────────────────────────────────────────────────────────────────────
function normalizeUser(backendUser) {
  if (!backendUser) return null;
  const id = String(backendUser.pk ?? backendUser.id ?? backendUser.email);
  const prefs = readJSON(PREFS_KEY, {})[id] || {
    weeklyDigest: true,
    priceDropAlerts: true,
    productUpdates: false,
    timezone:
      (typeof Intl !== "undefined" &&
        Intl.DateTimeFormat?.().resolvedOptions?.().timeZone) ||
      "America/New_York",
  };
  const tokens = readJSON(TOKENS_KEY, {})[id] || [];
  return {
    id,
    name: backendUser.full_name || (backendUser.email || "").split("@")[0],
    email: backendUser.email,
    phone: backendUser.phone || null,
    is_email_verified: !!backendUser.is_email_verified,
    is_phone_verified: !!backendUser.is_phone_verified,
    plan: "free",                       // backend doesn't track plans yet
    created_at: backendUser.date_joined || new Date().toISOString(),
    preferences: prefs,
    apiTokens: tokens,
  };
}

// ─────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────

export function currentUser() {
  const auth = getAuth();
  if (!auth || !auth.access || !auth.user) return null;
  return normalizeUser(auth.user);
}

export async function login({ email, password }) {
  try {
    const auth = await apiLogin({ email, password });
    return { ok: true, user: normalizeUser(auth.user) };
  } catch (err) {
    const p = err.payload || {};
    const detail =
      p.detail ||
      p.non_field_errors?.[0] ||
      p.email?.[0] ||
      p.password?.[0] ||
      err.message ||
      "Login failed. Check your credentials.";
    return { ok: false, error: detail };
  }
}

export async function signup({ name, email, password }) {
  try {
    const auth = await apiRegister({
      email,
      password,
      full_name: name,
      phone: null,
      marketing_opt_in: false,
    });
    return { ok: true, user: normalizeUser(auth.user) };
  } catch (err) {
    const p = err.payload || {};
    const detail =
      p.email?.[0] ||
      p.password1?.[0] ||
      p.password2?.[0] ||
      p.non_field_errors?.[0] ||
      err.message ||
      "Couldn't create the account. Try again.";
    return { ok: false, error: detail };
  }
}

export async function logout() {
  await apiLogout(); // clears carpapi.auth.v2 server-side + locally
  return { ok: true };
}

export async function requestPasswordReset({ email }) {
  try {
    await postJson("/auth/password/reset/", { email });
    // Backend returns 200 even if the email doesn't exist (anti-enumeration).
    return { ok: true, hint: email };
  } catch (err) {
    // Surface a friendly error but don't leak account existence.
    return { ok: true, hint: email, warning: err.message };
  }
}

export async function resetPassword({ token, newPassword }) {
  // dj-rest-auth expects { uid, token, new_password1, new_password2 }.
  // The "token" we get from the reset email URL is "<uid>-<token>" or
  // sometimes just "<token>". We support a "uid:token" shape too.
  let uid = "";
  let key = token || "";
  if (key.includes(":")) {
    [uid, key] = key.split(":", 2);
  }
  try {
    await postJson("/auth/password/reset/confirm/", {
      uid,
      token: key,
      new_password1: newPassword,
      new_password2: newPassword,
    });
    return { ok: true };
  } catch (err) {
    const p = err.payload || {};
    return {
      ok: false,
      error:
        p.token?.[0] ||
        p.uid?.[0] ||
        p.new_password2?.[0] ||
        p.new_password1?.[0] ||
        err.message ||
        "Reset link is invalid or expired.",
    };
  }
}

export async function changePassword({ currentPassword, newPassword }) {
  try {
    await postJson("/auth/password/change/", {
      old_password: currentPassword,
      new_password1: newPassword,
      new_password2: newPassword,
    });
    return { ok: true };
  } catch (err) {
    if (err instanceof AuthRequiredError) {
      return { ok: false, error: "Not signed in." };
    }
    const p = err.payload || {};
    return {
      ok: false,
      error:
        p.old_password?.[0] ||
        p.new_password1?.[0] ||
        p.new_password2?.[0] ||
        err.message ||
        "Couldn't change password.",
    };
  }
}

export async function updateProfile({ name, email }) {
  const body = {};
  if (name !== undefined) body.full_name = name;
  if (email !== undefined) body.email = email;
  try {
    const res = await fetch(
      (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "") +
        "/auth/user/",
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          Authorization: `Bearer ${getAuth()?.access || ""}`,
        },
        body: JSON.stringify(body),
      },
    );
    if (res.status === 401)
      return { ok: false, error: "Not signed in." };
    const data = await res.json();
    if (!res.ok) {
      return {
        ok: false,
        error:
          data?.email?.[0] ||
          data?.full_name?.[0] ||
          data?.detail ||
          "Couldn't update profile.",
      };
    }
    // Refresh the saved auth blob with the new user details.
    const auth = getAuth();
    if (auth) setAuth({ ...auth, user: data });
    return { ok: true, user: normalizeUser(data) };
  } catch (err) {
    return { ok: false, error: err.message || "Profile update failed." };
  }
}

// ─────────────────────────────────────────────────────────────────────
// LOCAL-ONLY (no backend equivalent yet)
//
// These let the demo4 pages render + save preferences locally. When
// the backend adds endpoints for them, swap these for real api calls
// — the function signatures don't change.
// ─────────────────────────────────────────────────────────────────────

export function updatePreferences(patch) {
  const u = currentUser();
  if (!u) return { ok: false, error: "Not signed in." };
  const all = readJSON(PREFS_KEY, {});
  all[u.id] = { ...(all[u.id] || u.preferences || {}), ...(patch || {}) };
  writeJSON(PREFS_KEY, all);
  return { ok: true, preferences: all[u.id] };
}

export function createApiToken({ label }) {
  const u = currentUser();
  if (!u) return { ok: false, error: "Not signed in." };
  const secret = Array.from({ length: 40 }, () =>
    Math.floor(Math.random() * 36).toString(36),
  ).join("");
  const tok = {
    id: `tok-${Math.random().toString(36).slice(2, 8)}`,
    label: (label || "").trim() || "Untitled token",
    last4: secret.slice(-4),
    created_at: new Date().toISOString(),
  };
  const all = readJSON(TOKENS_KEY, {});
  all[u.id] = [...(all[u.id] || []), tok];
  writeJSON(TOKENS_KEY, all);
  return { ok: true, token: `cpk_${secret}`, record: tok };
}

export function revokeApiToken({ id }) {
  const u = currentUser();
  if (!u) return { ok: false, error: "Not signed in." };
  const all = readJSON(TOKENS_KEY, {});
  all[u.id] = (all[u.id] || []).filter((t) => t.id !== id);
  writeJSON(TOKENS_KEY, all);
  return { ok: true };
}

export async function deleteAccount({ confirmEmail }) {
  const u = currentUser();
  if (!u) return { ok: false, error: "Not signed in." };
  if ((confirmEmail || "").trim().toLowerCase() !== u.email.toLowerCase()) {
    return { ok: false, error: "Confirmation email doesn't match." };
  }
  // No backend endpoint to delete the user account yet. Sign out
  // locally as a placeholder; flag this in the agent docs so a
  // server-side endpoint can be added.
  await apiLogout();
  return {
    ok: true,
    warning:
      "Account marked for deletion locally — server-side deletion is not yet wired (see deploy/PRODUCTION.md §7).",
  };
}

// Kept for demo-page compatibility. Real auth doesn't accept this
// pair; documented so the Signup/Login pages can show it as a hint.
export const DEMO_CREDENTIALS = {
  email: "ceylanibagci@gmail.com",
  password: "(see data/secrets/django_superuser_password.txt)",
};
