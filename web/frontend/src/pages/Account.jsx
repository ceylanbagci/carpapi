import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
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

const PLAN_PILL = {
  free: { label: "Free", className: "" },
  pro: { label: "Pro", className: "active" },
  team: { label: "Team", className: "active" },
};

function useUser() {
  const [user, setUser] = useState(() => currentUser());
  const refresh = () => setUser(currentUser());
  return [user, refresh];
}

function Toast({ message, kind = "ok", onClose }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, 2200);
    return () => clearTimeout(t);
  }, [message, onClose]);
  if (!message) return null;
  return <div className={`d4-toast d4-toast-${kind}`}>{message}</div>;
}

export default function Account() {
  const [user, refresh] = useUser();
  const [toast, setToast] = useState(null);
  const navigate = useNavigate();
  const loc = useLocation();
  const welcome = new URLSearchParams(loc.search).get("welcome");

  // Not signed in → bounce to login.
  useEffect(() => {
    if (!user) navigate("/login?next=/account", { replace: true });
  }, [user, navigate]);

  if (!user) return null;

  const ok = (msg) => setToast({ message: msg, kind: "ok" });
  const err = (msg) => setToast({ message: msg, kind: "err" });

  const plan = PLAN_PILL[user.plan] || PLAN_PILL.free;

  return (
    <div className="container-fluid p-0 d4-account">
      <Toast {...(toast || {})} onClose={() => setToast(null)} />

      <header className="d4-account-head">
        <div>
          <div className="d4-account-greeting">
            {welcome
              ? `Welcome aboard, ${user.name.split(" ")[0]} 🎉`
              : `Account settings`}
          </div>
          <div className="d4-account-sub">
            Signed in as <strong>{user.email}</strong>
            <span className={`d4-pill ${plan.className} ms-2`}>{plan.label}</span>
          </div>
        </div>
        <div className="d4-account-head-actions">
          <Link to="/pricing" className="btn btn-outline-primary btn-sm">
            <i className="bi bi-stars me-1"></i>
            Change plan
          </Link>
          <button
            type="button"
            className="btn btn-light btn-sm"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
          >
            <i className="bi bi-box-arrow-right me-1"></i>
            Sign out
          </button>
        </div>
      </header>

      <div className="row g-4">
        <div className="col-12 col-lg-7">
          <ProfileCard user={user} ok={ok} err={err} refresh={refresh} />
          <PasswordCard ok={ok} err={err} />
          <PreferencesCard user={user} ok={ok} refresh={refresh} />
        </div>
        <div className="col-12 col-lg-5">
          <PlanCard user={user} />
          <TokensCard user={user} ok={ok} err={err} refresh={refresh} />
          <DangerCard user={user} err={err} />
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------- //

function SectionCard({ title, subtitle, icon, children, footer }) {
  return (
    <section className="d4-card d4-account-card">
      <header className="d4-account-card-head">
        <div className="d4-account-card-icon">
          <i className={`bi ${icon}`}></i>
        </div>
        <div>
          <h2 className="d4-account-card-title">{title}</h2>
          {subtitle && <p className="d4-account-card-sub">{subtitle}</p>}
        </div>
      </header>
      <div className="d4-account-card-body">{children}</div>
      {footer && <div className="d4-account-card-foot">{footer}</div>}
    </section>
  );
}

function ProfileCard({ user, ok, err, refresh }) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [busy, setBusy] = useState(false);

  const save = (e) => {
    e.preventDefault();
    setBusy(true);
    const r = updateProfile({ name, email });
    setBusy(false);
    if (!r.ok) return err(r.error);
    refresh();
    ok("Profile updated");
  };

  const dirty = name !== user.name || email !== user.email;

  return (
    <SectionCard
      title="Profile"
      subtitle="The name and email associated with your account."
      icon="bi-person-circle"
    >
      <form onSubmit={save} className="d4-form-grid">
        <label className="d4-field">
          <span className="d4-field-label">Full name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="d4-field">
          <span className="d4-field-label">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <div className="d4-form-row-actions">
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!dirty || busy}
          >
            {busy ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </SectionCard>
  );
}

function PasswordCard({ ok, err }) {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const save = (e) => {
    e.preventDefault();
    if (next !== confirm) return err("New passwords don't match.");
    setBusy(true);
    const r = changePassword({ currentPassword: cur, newPassword: next });
    setBusy(false);
    if (!r.ok) return err(r.error);
    setCur("");
    setNext("");
    setConfirm("");
    ok("Password changed");
  };

  return (
    <SectionCard
      title="Password"
      subtitle="Change the password used to sign in."
      icon="bi-shield-lock"
    >
      <form onSubmit={save} className="d4-form-grid">
        <label className="d4-field">
          <span className="d4-field-label">Current password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={cur}
            onChange={(e) => setCur(e.target.value)}
          />
        </label>
        <label className="d4-field">
          <span className="d4-field-label">New password</span>
          <input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        <label className="d4-field">
          <span className="d4-field-label">Confirm new password</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </label>
        <div className="d4-form-row-actions">
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!cur || !next || !confirm || busy}
          >
            {busy ? "Updating…" : "Update password"}
          </button>
          <Link to="/forgot-password" className="btn btn-link btn-sm">
            Forgot current password?
          </Link>
        </div>
      </form>
    </SectionCard>
  );
}

function PreferencesCard({ user, ok, refresh }) {
  const prefs = user.preferences || {};

  const toggle = (key, value) => {
    const r = updatePreferences({ [key]: value });
    if (r.ok) {
      refresh();
      ok("Preferences saved");
    }
  };

  return (
    <SectionCard
      title="Preferences"
      subtitle="What CarPapi sends you, and how."
      icon="bi-sliders"
    >
      <ul className="d4-pref-list">
        <PrefRow
          label="Weekly inventory digest"
          desc="Every Monday morning — new listings + price drops since last week."
          checked={!!prefs.weeklyDigest}
          onChange={(v) => toggle("weeklyDigest", v)}
        />
        <PrefRow
          label="Price drop alerts"
          desc="When a saved listing's price falls more than 3%, you get an email within 15 minutes."
          checked={!!prefs.priceDropAlerts}
          onChange={(v) => toggle("priceDropAlerts", v)}
        />
        <PrefRow
          label="Product updates"
          desc="Occasional notes about new features. We promise to keep it short."
          checked={!!prefs.productUpdates}
          onChange={(v) => toggle("productUpdates", v)}
        />
        <li className="d4-pref-row">
          <div>
            <div className="d4-pref-label">Time zone</div>
            <div className="d4-pref-desc">
              Used to format dates everywhere in the app.
            </div>
          </div>
          <select
            value={prefs.timezone || "America/New_York"}
            onChange={(e) => toggle("timezone", e.target.value)}
            className="d4-select"
          >
            <option value="America/New_York">Eastern (New York)</option>
            <option value="America/Chicago">Central (Chicago)</option>
            <option value="America/Denver">Mountain (Denver)</option>
            <option value="America/Los_Angeles">Pacific (Los Angeles)</option>
            <option value="UTC">UTC</option>
          </select>
        </li>
      </ul>
    </SectionCard>
  );
}

function PrefRow({ label, desc, checked, onChange }) {
  return (
    <li className="d4-pref-row">
      <div>
        <div className="d4-pref-label">{label}</div>
        <div className="d4-pref-desc">{desc}</div>
      </div>
      <label className="d4-switch">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span></span>
      </label>
    </li>
  );
}

function PlanCard({ user }) {
  const plan = PLAN_PILL[user.plan] || PLAN_PILL.free;
  const created = user.created_at
    ? new Date(user.created_at).toLocaleDateString()
    : "—";
  return (
    <SectionCard
      title="Plan & billing"
      subtitle="Your current plan. Nothing is charged in this preview."
      icon="bi-stars"
    >
      <div className="d4-plan-row">
        <div>
          <div className="d4-plan-name">
            {plan.label} plan
            <span className={`d4-pill ${plan.className} ms-2`}>active</span>
          </div>
          <div className="d4-plan-meta">Member since {created}</div>
        </div>
        <Link to="/pricing" className="btn btn-primary btn-sm">
          See plans
        </Link>
      </div>
    </SectionCard>
  );
}

function TokensCard({ user, ok, err, refresh }) {
  const tokens = user.apiTokens || [];
  const [label, setLabel] = useState("");
  const [created, setCreated] = useState(null);

  const create = (e) => {
    e.preventDefault();
    const r = createApiToken({ label });
    if (!r.ok) return err(r.error);
    setLabel("");
    setCreated(r.token);
    refresh();
    ok("API token created");
  };

  const revoke = (id) => {
    const r = revokeApiToken({ id });
    if (!r.ok) return err(r.error);
    refresh();
    ok("Token revoked");
  };

  return (
    <SectionCard
      title="API tokens"
      subtitle="For scripts and programmatic access. Tokens are shown only once."
      icon="bi-key"
    >
      <form onSubmit={create} className="d4-token-form">
        <input
          type="text"
          placeholder='Label (e.g. "personal CLI")'
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          disabled={!label.trim()}
        >
          <i className="bi bi-plus-lg me-1"></i>
          Create token
        </button>
      </form>

      {created && (
        <div className="d4-token-reveal">
          <div className="d4-token-reveal-label">
            New token — copy it now, it won't be shown again:
          </div>
          <code className="d4-token-reveal-value">{created}</code>
          <button
            type="button"
            className="btn btn-light btn-sm"
            onClick={() => {
              navigator.clipboard?.writeText(created);
              ok("Copied to clipboard");
            }}
          >
            <i className="bi bi-clipboard"></i>
          </button>
        </div>
      )}

      <ul className="d4-token-list">
        {tokens.length === 0 && (
          <li className="d4-token-empty">No tokens yet.</li>
        )}
        {tokens.map((t) => (
          <li key={t.id} className="d4-token-row">
            <div>
              <div className="d4-token-label-text">{t.label}</div>
              <div className="d4-token-meta">
                <code>…{t.last4}</code> · created{" "}
                {new Date(t.created_at).toLocaleDateString()}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-link btn-sm text-danger"
              onClick={() => revoke(t.id)}
            >
              Revoke
            </button>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

function DangerCard({ user, err }) {
  const [confirm, setConfirm] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const onDelete = () => {
    const r = deleteAccount({ confirmEmail: confirm });
    if (!r.ok) return err(r.error);
    navigate("/", { replace: true });
  };

  return (
    <section className="d4-card d4-account-card d4-account-danger">
      <header className="d4-account-card-head">
        <div className="d4-account-card-icon danger">
          <i className="bi bi-exclamation-octagon"></i>
        </div>
        <div>
          <h2 className="d4-account-card-title">Danger zone</h2>
          <p className="d4-account-card-sub">
            Deleting your account removes your saved searches, alerts, and
            tokens. This cannot be undone.
          </p>
        </div>
      </header>
      <div className="d4-account-card-body">
        {!open ? (
          <button
            type="button"
            className="btn btn-outline-danger btn-sm"
            onClick={() => setOpen(true)}
          >
            Delete my account
          </button>
        ) : (
          <div className="d4-danger-confirm">
            <p>
              Type <strong>{user.email}</strong> below to confirm.
            </p>
            <input
              type="email"
              placeholder={user.email}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            <div className="d4-form-row-actions">
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={onDelete}
                disabled={confirm.trim().toLowerCase() !== user.email}
              >
                Permanently delete
              </button>
              <button
                type="button"
                className="btn btn-link btn-sm"
                onClick={() => {
                  setOpen(false);
                  setConfirm("");
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
