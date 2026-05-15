/**
 * /settings — standalone settings page for any signed-in user.
 *
 * NOT wrapped in the admin Layout (no sidebar with Cars/Dealers/...
 * etc). Uses the same `d4-chat` light-theme shell that /login and
 * /chat use so the visual language stays consistent across the
 * non-admin surface of the app.
 *
 * All calls go through `data/mockAuth.js` which is now a thin
 * bridge over the real backend:
 *   - currentUser() → reads the JWT-backed user object
 *   - updateProfile() → PATCH /api/auth/user/
 *   - changePassword() → POST /api/auth/password/change/
 *   - updatePreferences() → LOCAL-ONLY (until a backend endpoint exists)
 *   - createApiToken / revokeApiToken → LOCAL-ONLY
 *   - deleteAccount → LOCAL-ONLY
 *
 * Sections (matches the demo4 design pattern from Account.jsx but in
 * a single-column, no-sidebar shell):
 *   1. Profile (full_name, email, phone)
 *   2. Password
 *   3. Notification preferences
 *   4. API tokens (local-only)
 *   5. Danger zone — sign out + delete account
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  changePassword,
  createApiToken,
  currentUser,
  deleteAccount,
  logout,
  revokeApiToken,
  updatePreferences,
  updateProfile,
} from "../data/mockAuth.js";
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  sendTestNotification,
} from "../api.js";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";

// ─────────────────────────────────────────────────────────────────────
// Small inline helpers (same visual language as Login.jsx)
// ─────────────────────────────────────────────────────────────────────

const card = {
  background: "#fff",
  border: "1px solid rgba(0,0,0,0.08)",
  borderRadius: 16,
  padding: "22px 24px",
  marginBottom: 18,
  boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
};

const cardHead = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 14,
  gap: 12,
};

const cardTitle = {
  fontSize: 16,
  fontWeight: 700,
  color: "#111",
  margin: 0,
};

const cardSub = {
  fontSize: 13,
  color: "#666",
  margin: 0,
  marginTop: 2,
};

const input = {
  width: "100%",
  padding: "11px 14px",
  borderRadius: 10,
  border: "1px solid rgba(0,0,0,0.15)",
  fontSize: 14,
  background: "#fff",
  color: "#111",
  outline: "none",
  boxSizing: "border-box",
};

const label = {
  fontSize: 12,
  fontWeight: 600,
  color: "#444",
  marginBottom: 6,
  display: "block",
  textTransform: "uppercase",
  letterSpacing: 0.4,
};

const btn = {
  padding: "10px 18px",
  borderRadius: 10,
  border: "1px solid rgba(0,0,0,0.15)",
  background: "#fff",
  color: "#111",
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
};
const btnPrimary = { ...btn, background: "#111", color: "#fff", border: "1px solid #111" };
const btnDanger = { ...btn, background: "#fff", color: "#b91c1c", border: "1px solid #fecaca" };

// ─────────────────────────────────────────────────────────────────────
// Toast (one floating message)
// ─────────────────────────────────────────────────────────────────────

function Toast({ msg, kind, onClose }) {
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(onClose, 2400);
    return () => clearTimeout(t);
  }, [msg, onClose]);
  if (!msg) return null;
  const bg = kind === "err" ? "rgba(220,38,38,0.1)" : "rgba(16,185,129,0.12)";
  const fg = kind === "err" ? "#b91c1c" : "#047857";
  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        left: "50%",
        transform: "translateX(-50%)",
        background: bg,
        color: fg,
        padding: "10px 18px",
        borderRadius: 10,
        fontSize: 14,
        fontWeight: 500,
        zIndex: 100,
        border: `1px solid ${fg}33`,
      }}
    >
      {msg}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────

export default function Settings() {
  const navigate = useNavigate();
  const [user, setUser] = useState(() => currentUser());
  const [toast, setToast] = useState(null);

  const refresh = () => setUser(currentUser());
  const ok = (m) => setToast({ msg: m, kind: "ok" });
  const err = (m) => setToast({ msg: m, kind: "err" });

  // If somehow the user is null (race after sign-out), bounce.
  useEffect(() => {
    if (!user) navigate("/login?next=/settings", { replace: true });
  }, [user, navigate]);
  if (!user) return null;

  const onSignOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="d4-chat" data-theme="light">
      <PublicTopBar />

      <main className="d4-chat-scroller">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          style={{ width: "100%", maxWidth: 720, margin: "12px auto 80px" }}
        >
          <div style={{ marginBottom: 22 }}>
            <h1 style={{ fontSize: 28, fontWeight: 800, margin: 0, color: "#111" }}>
              Settings
            </h1>
            <p style={{ color: "#666", marginTop: 6, fontSize: 14 }}>
              Manage how CarPapi knows you, alerts you, and authenticates you.
            </p>
          </div>

          <ProfileCard user={user} refresh={refresh} ok={ok} err={err} />
          <PasswordCard ok={ok} err={err} />
          <PreferencesCard ok={ok} err={err} />
          <ApiTokensCard user={user} refresh={refresh} ok={ok} err={err} />
          <DangerCard user={user} ok={ok} err={err} navigate={navigate} />
        </motion.div>
      </main>

      <PublicFooter />

      <Toast msg={toast?.msg} kind={toast?.kind} onClose={() => setToast(null)} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Section: Profile
// ─────────────────────────────────────────────────────────────────────

function ProfileCard({ user, refresh, ok, err }) {
  const [name, setName] = useState(user.name || "");
  const [email, setEmail] = useState(user.email || "");
  const [busy, setBusy] = useState(false);

  const dirty = name !== (user.name || "") || email !== (user.email || "");

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    const r = await updateProfile({ name, email });
    setBusy(false);
    if (!r.ok) return err(r.error);
    refresh();
    ok("Profile updated");
  };

  return (
    <section style={card}>
      <header style={cardHead}>
        <div>
          <h2 style={cardTitle}>Profile</h2>
          <p style={cardSub}>
            How CarPapi addresses you. Email is your login — change it
            carefully.
          </p>
        </div>
        {user.is_email_verified ? (
          <span
            style={{
              fontSize: 12,
              padding: "3px 8px",
              borderRadius: 99,
              background: "#ecfdf5",
              color: "#047857",
              fontWeight: 600,
            }}
          >
            Email verified
          </span>
        ) : null}
      </header>

      <form onSubmit={save}>
        <div style={{ marginBottom: 12 }}>
          <label style={label}>Full name</label>
          <input
            style={input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            disabled={busy}
          />
        </div>
        <div style={{ marginBottom: 14 }}>
          <label style={label}>Email</label>
          <input
            type="email"
            style={input}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            disabled={busy}
          />
        </div>
        <button
          type="submit"
          disabled={!dirty || busy}
          style={{ ...btnPrimary, opacity: !dirty || busy ? 0.55 : 1 }}
        >
          {busy ? "Saving…" : "Save changes"}
        </button>
      </form>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Section: Password
// ─────────────────────────────────────────────────────────────────────

function PasswordCard({ ok, err }) {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    if (next !== confirm) return err("New passwords don't match.");
    if (next.length < 8) return err("Use at least 8 characters.");
    setBusy(true);
    const r = await changePassword({ currentPassword: cur, newPassword: next });
    setBusy(false);
    if (!r.ok) return err(r.error);
    setCur("");
    setNext("");
    setConfirm("");
    ok("Password changed");
  };

  return (
    <section style={card}>
      <header style={cardHead}>
        <div>
          <h2 style={cardTitle}>Password</h2>
          <p style={cardSub}>
            Pick something at least 8 characters. We never store it in
            plaintext.
          </p>
        </div>
      </header>
      <form onSubmit={save}>
        <div style={{ marginBottom: 12 }}>
          <label style={label}>Current password</label>
          <input
            type="password"
            style={input}
            value={cur}
            onChange={(e) => setCur(e.target.value)}
            autoComplete="current-password"
            disabled={busy}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <label style={label}>New password</label>
            <input
              type="password"
              style={input}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
              disabled={busy}
            />
          </div>
          <div>
            <label style={label}>Confirm new password</label>
            <input
              type="password"
              style={input}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              disabled={busy}
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={!cur || !next || !confirm || busy}
          style={{ ...btnPrimary, opacity: !cur || !next || !confirm || busy ? 0.55 : 1 }}
        >
          {busy ? "Updating…" : "Change password"}
        </button>
      </form>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Section: Notification preferences — backed by /api/notifications/.
//
// Categories are returned by the backend so the UI never drifts from
// the model (new agent type lands → backend ships → checkbox shows up
// next render). Each toggle PATCHes back; cc_email is text-input
// committed on blur.
// ─────────────────────────────────────────────────────────────────────

function PreferencesCard({ ok, err }) {
  const [categories, setCategories] = useState([]);
  const [ccEmail, setCcEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testStatus, setTestStatus] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await getNotificationPreferences();
        if (!alive) return;
        setCategories(data.categories || []);
        setCcEmail(data.cc_email || "");
      } catch (e) {
        if (alive) err("Couldn't load notification settings");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [err]);

  const toggle = async (key) => {
    if (busy) return;
    setBusy(true);
    const next = categories.map((c) =>
      c.key === key ? { ...c, enabled: !c.enabled } : c
    );
    setCategories(next);  // optimistic
    try {
      const payload = { [key]: !categories.find((c) => c.key === key).enabled };
      const updated = await updateNotificationPreferences({ categories: payload });
      setCategories(updated.categories || next);
      ok("Saved");
    } catch (e) {
      setCategories(categories);  // rollback
      err("Couldn't save preference");
    } finally {
      setBusy(false);
    }
  };

  const commitCcEmail = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await updateNotificationPreferences({ cc_email: ccEmail.trim() });
      ok(ccEmail.trim() ? "CC address saved" : "CC address cleared");
    } catch (e) {
      err("Couldn't save CC address");
    } finally {
      setBusy(false);
    }
  };

  const fireTest = async () => {
    if (busy) return;
    setBusy(true);
    setTestStatus(null);
    try {
      const r = await sendTestNotification();
      if (r.ok) {
        setTestStatus({ kind: "ok", msg: `Sent (SES id: ${r.ses_message_id})` });
        ok("Test email sent");
      } else if (r.status === "skipped_sandbox") {
        setTestStatus({
          kind: "warn",
          msg: "SES is in sandbox mode — your address must be verified. "
             + "Ask admin to verify it or wait for production access.",
        });
      } else {
        setTestStatus({ kind: "err", msg: r.error || r.status });
      }
    } catch (e) {
      setTestStatus({ kind: "err", msg: String(e.message || e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={card}>
      <header style={cardHead}>
        <div>
          <h2 style={cardTitle}>Notifications</h2>
          <p style={cardSub}>
            How CarPapi reaches out by email. Toggles take effect immediately.
          </p>
        </div>
        <button
          type="button"
          onClick={fireTest}
          disabled={busy || loading}
          style={{
            padding: "8px 14px",
            borderRadius: 10,
            border: "1px solid #d0d7de",
            background: "#fff",
            cursor: busy ? "default" : "pointer",
            fontSize: 13,
            fontWeight: 600,
            opacity: busy || loading ? 0.6 : 1,
          }}
        >
          Send test email
        </button>
      </header>

      {testStatus && (
        <div
          style={{
            margin: "0 0 14px",
            padding: "10px 14px",
            borderRadius: 10,
            background: testStatus.kind === "ok"
              ? "rgba(16,185,129,0.10)"
              : testStatus.kind === "warn"
              ? "rgba(234,179,8,0.10)"
              : "rgba(220,38,38,0.10)",
            color: testStatus.kind === "ok"
              ? "#047857"
              : testStatus.kind === "warn"
              ? "#854d0e"
              : "#b91c1c",
            fontSize: 13,
          }}
        >
          {testStatus.msg}
        </div>
      )}

      {loading ? (
        <div style={{ padding: "10px 0", color: "#666", fontSize: 14 }}>
          Loading…
        </div>
      ) : (
        categories.map((row) => (
          <div
            key={row.key}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 0",
              borderTop: "1px solid rgba(0,0,0,0.05)",
            }}
          >
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, color: "#111" }}>
                {row.label}
              </div>
              <div style={{ fontSize: 12, color: "#888" }}>
                category: <code>{row.key}</code>
              </div>
            </div>
            <button
              type="button"
              onClick={() => toggle(row.key)}
              aria-pressed={row.enabled}
              disabled={busy}
              style={{
                width: 44, height: 24, borderRadius: 99, border: "none",
                cursor: busy ? "default" : "pointer",
                background: row.enabled ? "#111" : "#cbd5e1",
                position: "relative", transition: "background 0.15s",
                opacity: busy ? 0.6 : 1,
              }}
            >
              <span
                style={{
                  position: "absolute", top: 3, left: row.enabled ? 23 : 3,
                  width: 18, height: 18, borderRadius: 99, background: "#fff",
                  transition: "left 0.15s",
                }}
              />
            </button>
          </div>
        ))
      )}

      <div
        style={{
          marginTop: 18, paddingTop: 14,
          borderTop: "1px solid rgba(0,0,0,0.05)",
        }}
      >
        <label
          style={{
            fontSize: 13, fontWeight: 600, color: "#111",
            display: "block", marginBottom: 4,
          }}
        >
          CC address (optional)
        </label>
        <p style={{ fontSize: 12, color: "#666", margin: "0 0 8px" }}>
          Mirror every notification to this address too. Useful for on-call
          handoffs. Leave blank to disable.
        </p>
        <input
          type="email"
          value={ccEmail}
          onChange={(e) => setCcEmail(e.target.value)}
          onBlur={commitCcEmail}
          placeholder="oncall@example.com"
          disabled={busy || loading}
          style={{
            width: "100%", padding: "10px 14px", borderRadius: 10,
            border: "1px solid rgba(0,0,0,0.15)", fontSize: 14,
            background: "#fff", color: "#111", outline: "none",
            boxSizing: "border-box",
          }}
        />
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Section: API tokens (LOCAL-ONLY for now)
// ─────────────────────────────────────────────────────────────────────

function ApiTokensCard({ user, refresh, ok, err }) {
  const [label2, setLabel2] = useState("");
  const [reveal, setReveal] = useState(null);
  const tokens = user.apiTokens || [];

  const create = () => {
    if (!label2.trim()) return err("Give the token a label.");
    const r = createApiToken({ label: label2.trim() });
    if (!r.ok) return err(r.error);
    setReveal(r.token);
    setLabel2("");
    refresh();
  };
  const revoke = (id) => {
    const r = revokeApiToken({ id });
    if (!r.ok) return err(r.error);
    refresh();
    ok("Token revoked");
  };

  return (
    <section style={card}>
      <header style={cardHead}>
        <div>
          <h2 style={cardTitle}>API tokens</h2>
          <p style={cardSub}>
            Programmatic access. Tokens are shown once — copy them right
            away. Saved locally; backend tokens landing soon.
          </p>
        </div>
      </header>

      {reveal && (
        <div
          style={{
            padding: 12,
            background: "#fffbeb",
            border: "1px solid #fde68a",
            borderRadius: 10,
            marginBottom: 12,
            fontFamily: "ui-monospace, SFMono-Regular, monospace",
            fontSize: 12,
            color: "#78350f",
            wordBreak: "break-all",
          }}
        >
          {reveal}
          <div style={{ marginTop: 8 }}>
            <button type="button" style={btn} onClick={() => setReveal(null)}>
              I've copied it
            </button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          style={{ ...input, flex: 1 }}
          placeholder="Token label (e.g. zapier-prod)"
          value={label2}
          onChange={(e) => setLabel2(e.target.value)}
        />
        <button type="button" style={btnPrimary} onClick={create}>
          Generate
        </button>
      </div>

      {tokens.length === 0 ? (
        <div style={{ color: "#888", fontSize: 13 }}>No tokens yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {tokens.map((t) => (
            <li
              key={t.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 0",
                borderTop: "1px solid rgba(0,0,0,0.05)",
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{t.label}</div>
                <div style={{ fontSize: 12, color: "#888" }}>
                  …{t.last4} · created {new Date(t.created_at).toLocaleDateString()}
                </div>
              </div>
              <button type="button" style={btnDanger} onClick={() => revoke(t.id)}>
                Revoke
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Section: Danger zone
// ─────────────────────────────────────────────────────────────────────

function DangerCard({ user, ok, err, navigate }) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");

  const remove = async () => {
    const r = await deleteAccount({ confirmEmail: confirm });
    if (!r.ok) return err(r.error);
    if (r.warning) ok(r.warning);
    navigate("/", { replace: true });
  };

  return (
    <section style={{ ...card, borderColor: "#fecaca" }}>
      <header style={cardHead}>
        <div>
          <h2 style={{ ...cardTitle, color: "#b91c1c" }}>Danger zone</h2>
          <p style={cardSub}>
            Account deletion is final. Saved chats and listings will be
            unlinked.
          </p>
        </div>
      </header>

      {!open ? (
        <button type="button" style={btnDanger} onClick={() => setOpen(true)}>
          Delete account…
        </button>
      ) : (
        <div>
          <label style={label}>
            Type your email <strong>{user.email}</strong> to confirm:
          </label>
          <input
            style={{ ...input, marginBottom: 12 }}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={user.email}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" style={btn} onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button
              type="button"
              style={btnDanger}
              onClick={remove}
              disabled={confirm.trim().toLowerCase() !== (user.email || "").toLowerCase()}
            >
              Delete forever
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
