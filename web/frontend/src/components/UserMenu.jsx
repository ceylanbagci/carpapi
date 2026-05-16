/**
 * <UserMenu /> — head-icon dropdown for any logged-in chrome.
 *
 * Matches the look of the demo4 admin shell: circular avatar with the
 * user's initials, click → small dropdown with Chat / Dashboard /
 * Settings / Sign out. Closes on outside-click + Escape.
 *
 * When the user is logged OUT this component renders the inline
 * "Sign in / Get started" pair instead — so callers can drop one
 * <UserMenu /> in the top-right and the right thing happens in both
 * states.
 *
 * Two visual variants:
 *   - `tone="light"` (default) — for the white `d4-chat` shell used by
 *     /login, /register, /pricing, /settings.
 *   - `tone="dark"` — for the marketing dark-mode chrome (matches
 *     `public/landing.html`).
 */
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { useTheme } from "../theme.jsx";

function initialsOf(user) {
  const name = (user.full_name || "").trim();
  if (name) {
    return name
      .split(/\s+/)
      .map((p) => p[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }
  return ((user.email || "?")[0] || "?").toUpperCase();
}

const TONE_STYLES = {
  light: {
    btn: {
      background: "#f3f4f6",
      color: "#111",
      border: "1px solid rgba(0,0,0,0.08)",
    },
    pop: {
      background: "#fff",
      color: "#111",
      border: "1px solid rgba(0,0,0,0.10)",
      boxShadow: "0 12px 30px rgba(0,0,0,0.10)",
    },
    rowHover: "rgba(0,0,0,0.04)",
    divider: "rgba(0,0,0,0.08)",
    muted: "#666",
    danger: "#b91c1c",
  },
  dark: {
    btn: {
      background: "#11141c",
      color: "#f6f7fb",
      border: "1px solid rgba(255,255,255,0.08)",
    },
    pop: {
      background: "#11141c",
      color: "#f6f7fb",
      border: "1px solid rgba(255,255,255,0.08)",
      boxShadow: "0 12px 30px rgba(0,0,0,0.40)",
    },
    rowHover: "rgba(255,255,255,0.06)",
    divider: "rgba(255,255,255,0.08)",
    muted: "#9aa3b2",
    danger: "#fca5a5",
  },
};

export default function UserMenu({ tone = "light" }) {
  const { user, signOut } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // ── Logged out: render the inline Sign in / Get started pair so the
  //    same component can sit in any top-bar regardless of auth state.
  if (!user) {
    const linkStyle = {
      padding: "8px 14px",
      borderRadius: 8,
      fontSize: 14,
      fontWeight: 500,
      textDecoration: "none",
      color: tone === "dark" ? "#9aa3b2" : "#444",
    };
    const primary = {
      ...linkStyle,
      background: tone === "dark" ? "#ffd86b" : "#111",
      color: tone === "dark" ? "#1a1c20" : "#fff",
      fontWeight: 700,
    };
    return (
      <div style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
        <Link to="/login" style={linkStyle}>Sign in</Link>
        <Link to="/register" style={primary}>Get started</Link>
      </div>
    );
  }

  // ── Logged in: head icon + dropdown.
  const s = TONE_STYLES[tone] || TONE_STYLES.light;
  const initials = initialsOf(user);
  const displayName = (user.full_name || "").trim() || user.email.split("@")[0];

  const onSignOut = async () => {
    setOpen(false);
    await signOut();
    navigate("/", { replace: true });
  };

  return (
    <div
      ref={wrapRef}
      style={{ position: "relative", display: "inline-block" }}
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        aria-haspopup="true"
        aria-expanded={open}
        title={user.email}
        style={{
          ...s.btn,
          width: 36, height: 36, borderRadius: "50%",
          fontWeight: 700, fontSize: 13, cursor: "pointer",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontFamily: "inherit", transition: "background 0.15s",
        }}
      >
        {initials}
      </button>

      {open && (
        <div
          role="menu"
          style={{
            ...s.pop,
            position: "absolute", right: 0, top: "calc(100% + 8px)",
            minWidth: 240, borderRadius: 12, padding: 6, zIndex: 50,
          }}
        >
          {/* Theme switch — always the first row so it's discoverable
              from any signed-in page. Two-state segmented control rather
              than a single button so the active mode is unambiguous. */}
          <ThemeSwitch s={s} theme={theme} onChange={toggleTheme} />
          <hr style={{ border: 0, borderTop: `1px solid ${s.divider}`, margin: "6px 0" }} />
          <div style={{ padding: "10px 12px", fontSize: 12, color: s.muted, whiteSpace: "nowrap" }}>
            <div style={{ color: s.pop.color, fontSize: 13, fontWeight: 600, marginBottom: 2 }}>
              {displayName}
            </div>
            {user.email}
          </div>
          <hr style={{ border: 0, borderTop: `1px solid ${s.divider}`, margin: "6px 0" }} />
          <MenuRow s={s} to="/chat" icon="bi-chat-dots">Chat</MenuRow>
          {user.is_staff && (
            <MenuRow s={s} to="/dashboard" icon="bi-speedometer2">Dashboard</MenuRow>
          )}
          <MenuRow s={s} to="/settings" icon="bi-person-gear">Settings</MenuRow>
          <hr style={{ border: 0, borderTop: `1px solid ${s.divider}`, margin: "6px 0" }} />
          <button
            type="button"
            role="menuitem"
            onClick={onSignOut}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 12px", borderRadius: 8,
              fontSize: 14, color: s.danger, background: "transparent",
              border: "none", cursor: "pointer", width: "100%", textAlign: "left",
              fontFamily: "inherit",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = s.rowHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <i className="bi bi-box-arrow-right" aria-hidden="true"></i>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Two-state segmented control: ☀ Light  |  🌙 Dark.
 * Clicking the inactive side flips the theme; the active side is a
 * no-op so a deliberate keyboard focus loop doesn't accidentally
 * toggle on re-entry.
 */
function ThemeSwitch({ s, theme, onChange }) {
  const activeBg = s.pop.color === "#f6f7fb"
    ? "rgba(255,255,255,0.10)"
    : "rgba(0,0,0,0.06)";
  const activeColor = s.pop.color;
  const idleColor   = s.muted;
  const opt = (val, label, icon) => {
    const active = theme === val;
    return (
      <button
        type="button"
        role="menuitemradio"
        aria-checked={active}
        onClick={() => { if (!active) onChange(); }}
        style={{
          flex: 1,
          display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
          padding: "6px 8px", borderRadius: 7,
          background: active ? activeBg : "transparent",
          color: active ? activeColor : idleColor,
          border: "none", cursor: active ? "default" : "pointer",
          fontSize: 12, fontWeight: 600, fontFamily: "inherit",
        }}
      >
        <i className={`bi ${icon}`} aria-hidden="true" />
        {label}
      </button>
    );
  };
  return (
    <div
      role="group"
      aria-label="Theme"
      style={{
        display: "flex", gap: 4,
        margin: "2px 4px 4px",
        padding: 3, borderRadius: 9,
        background: s.pop.color === "#f6f7fb"
          ? "rgba(255,255,255,0.04)"
          : "rgba(0,0,0,0.03)",
        border: `1px solid ${s.divider}`,
      }}
    >
      {opt("light", "Light", "bi-sun")}
      {opt("dark",  "Dark",  "bi-moon-stars-fill")}
    </div>
  );
}

function MenuRow({ s, to, icon, children }) {
  return (
    <Link
      to={to}
      role="menuitem"
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "10px 12px", borderRadius: 8,
        fontSize: 14, color: s.pop.color, textDecoration: "none",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = s.rowHover; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      <i className={`bi ${icon}`} aria-hidden="true"></i>
      {children}
    </Link>
  );
}
