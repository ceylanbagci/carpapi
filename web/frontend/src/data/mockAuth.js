/**
 * UI-only mock auth: stores a "session" in localStorage so the
 * login / signup / account / password-reset pages can demonstrate
 * real interaction without a backend.
 *
 * Drop-in design: every function returns the same shape a real API
 * client would return. When the backend lands, replace this module
 * with one that wraps `fetch('/api/auth/...')` — no UI changes needed.
 */

const USERS_KEY = "carpapi.auth.users.v1";
const SESSION_KEY = "carpapi.auth.session.v1";
const RESET_KEY = "carpapi.auth.resetTokens.v1";

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
    /* quota — ignore in mock */
  }
}

function nowIso() {
  return new Date().toISOString();
}

function seedDemoUser() {
  const users = readJSON(USERS_KEY, []);
  if (users.length === 0) {
    users.push({
      id: "demo-1",
      name: "Demo Driver",
      email: "demo@carpapi.app",
      // Mock-only: NEVER store plaintext in a real backend.
      password: "demo1234",
      plan: "free",
      created_at: "2025-12-01T10:00:00Z",
      preferences: {
        weeklyDigest: true,
        priceDropAlerts: true,
        productUpdates: false,
        timezone: "America/New_York",
      },
      apiTokens: [
        {
          id: "tok-1",
          label: "Personal dashboard",
          last4: "9k4M",
          created_at: "2025-12-15T14:22:00Z",
        },
      ],
    });
    writeJSON(USERS_KEY, users);
  }
}
seedDemoUser();

// ----- Public API ---------------------------------------------------

export function currentUser() {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return null;
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return null;
  // Never expose the password field.
  const { password, ...safe } = u;
  return safe;
}

export function login({ email, password }) {
  const users = readJSON(USERS_KEY, []);
  const u = users.find(
    (x) => x.email.toLowerCase() === (email || "").toLowerCase(),
  );
  if (!u) return { ok: false, error: "No account with that email." };
  if (u.password !== password)
    return { ok: false, error: "Wrong password. Try again." };
  writeJSON(SESSION_KEY, { userId: u.id, at: nowIso() });
  return { ok: true, user: currentUser() };
}

export function signup({ name, email, password }) {
  const trimmedEmail = (email || "").trim().toLowerCase();
  if (!trimmedEmail || !/.+@.+\..+/.test(trimmedEmail)) {
    return { ok: false, error: "Enter a valid email address." };
  }
  if (!password || password.length < 8) {
    return { ok: false, error: "Password must be at least 8 characters." };
  }
  const users = readJSON(USERS_KEY, []);
  if (users.find((x) => x.email.toLowerCase() === trimmedEmail)) {
    return { ok: false, error: "An account with that email already exists." };
  }
  const id = `u-${Math.random().toString(36).slice(2, 10)}`;
  const user = {
    id,
    name: (name || "").trim() || trimmedEmail.split("@")[0],
    email: trimmedEmail,
    password,
    plan: "free",
    created_at: nowIso(),
    preferences: {
      weeklyDigest: true,
      priceDropAlerts: true,
      productUpdates: false,
      timezone:
        Intl?.DateTimeFormat?.().resolvedOptions?.().timeZone ||
        "America/New_York",
    },
    apiTokens: [],
  };
  users.push(user);
  writeJSON(USERS_KEY, users);
  writeJSON(SESSION_KEY, { userId: id, at: nowIso() });
  return { ok: true, user: currentUser() };
}

export function logout() {
  localStorage.removeItem(SESSION_KEY);
  return { ok: true };
}

export function requestPasswordReset({ email }) {
  const users = readJSON(USERS_KEY, []);
  const u = users.find(
    (x) => x.email.toLowerCase() === (email || "").toLowerCase(),
  );
  // Always pretend the request succeeded (don't leak account existence).
  if (!u) return { ok: true, token: null };
  const token = `r-${Math.random().toString(36).slice(2, 12)}`;
  const tokens = readJSON(RESET_KEY, {});
  tokens[token] = { userId: u.id, at: nowIso() };
  writeJSON(RESET_KEY, tokens);
  return { ok: true, token, hint: u.email };
}

export function resetPassword({ token, newPassword }) {
  if (!newPassword || newPassword.length < 8) {
    return { ok: false, error: "Password must be at least 8 characters." };
  }
  const tokens = readJSON(RESET_KEY, {});
  const entry = tokens[token];
  if (!entry) return { ok: false, error: "Reset link is invalid or expired." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === entry.userId);
  if (!u) return { ok: false, error: "Account not found." };
  u.password = newPassword;
  writeJSON(USERS_KEY, users);
  delete tokens[token];
  writeJSON(RESET_KEY, tokens);
  return { ok: true };
}

export function updateProfile({ name, email }) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale; sign in again." };
  if (name !== undefined) u.name = name.trim();
  if (email !== undefined) {
    const trimmed = email.trim().toLowerCase();
    if (!/.+@.+\..+/.test(trimmed))
      return { ok: false, error: "Enter a valid email address." };
    const taken = users.find((x) => x.id !== u.id && x.email === trimmed);
    if (taken) return { ok: false, error: "That email is already taken." };
    u.email = trimmed;
  }
  writeJSON(USERS_KEY, users);
  return { ok: true, user: currentUser() };
}

export function changePassword({ currentPassword, newPassword }) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale." };
  if (u.password !== currentPassword)
    return { ok: false, error: "Current password is wrong." };
  if (!newPassword || newPassword.length < 8)
    return { ok: false, error: "New password must be at least 8 characters." };
  u.password = newPassword;
  writeJSON(USERS_KEY, users);
  return { ok: true };
}

export function updatePreferences(patch) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale." };
  u.preferences = { ...(u.preferences || {}), ...patch };
  writeJSON(USERS_KEY, users);
  return { ok: true, preferences: u.preferences };
}

export function createApiToken({ label }) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale." };
  // Generate a token; reveal once, store only the last 4 chars.
  const secret = Array.from({ length: 40 }, () =>
    Math.floor(Math.random() * 36).toString(36),
  ).join("");
  const tok = {
    id: `tok-${Math.random().toString(36).slice(2, 8)}`,
    label: label?.trim() || "Untitled token",
    last4: secret.slice(-4),
    created_at: nowIso(),
  };
  u.apiTokens = [...(u.apiTokens || []), tok];
  writeJSON(USERS_KEY, users);
  return { ok: true, token: `cpk_${secret}`, record: tok };
}

export function revokeApiToken({ id }) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale." };
  u.apiTokens = (u.apiTokens || []).filter((t) => t.id !== id);
  writeJSON(USERS_KEY, users);
  return { ok: true };
}

export function deleteAccount({ confirmEmail }) {
  const session = readJSON(SESSION_KEY, null);
  if (!session) return { ok: false, error: "Not signed in." };
  const users = readJSON(USERS_KEY, []);
  const u = users.find((x) => x.id === session.userId);
  if (!u) return { ok: false, error: "Session is stale." };
  if ((confirmEmail || "").trim().toLowerCase() !== u.email) {
    return { ok: false, error: "Confirmation email doesn't match." };
  }
  const filtered = users.filter((x) => x.id !== u.id);
  writeJSON(USERS_KEY, filtered);
  localStorage.removeItem(SESSION_KEY);
  return { ok: true };
}

export const DEMO_CREDENTIALS = { email: "demo@carpapi.app", password: "demo1234" };
