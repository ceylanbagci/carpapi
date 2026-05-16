/**
 * /login — real email + password (no more shared passphrase).
 *
 * Calls api.login(email, password) which POSTs to
 * /api/auth/login/ on the Django backend. On success the JWT
 * tokens + user object are persisted to localStorage by api.js;
 * we then bounce to `?next=` (default /chat).
 *
 * Google button links to the backend's /accounts/google/login/
 * endpoint — allauth handles the full OAuth dance and bounces
 * the user back to `?next=`.
 */
import { useState } from "react";
import {
  Link,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { motion } from "framer-motion";
import { googleLoginUrl, login as apiLogin } from "../api.js";
import { useAuth } from "../auth.jsx";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";

const inputBaseStyle = {
  width: "100%",
  padding: "12px 16px",
  borderRadius: 12,
  border: "1px solid rgba(0,0,0,0.15)",
  fontSize: 16,
  background: "#fff",
  color: "#111",
  outline: "none",
  boxSizing: "border-box",
};

const buttonBase = {
  marginTop: 14,
  width: "100%",
  padding: "12px 16px",
  borderRadius: 12,
  border: "none",
  fontSize: 16,
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 10,
};

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const next = params.get("next") || "/chat";

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      // api.login() wipes any stale localStorage auth before calling
      // /api/auth/login/, so a previous-session JWT can't trip
      // SimpleJWT into a "Given token not valid for any token type"
      // 401 before the login view runs.
      const auth = await apiLogin({ email: email.trim(), password });
      signIn(auth);
      navigate(next, { replace: true });
    } catch (err) {
      const reason =
        err.payload?.detail ||
        err.payload?.non_field_errors?.[0] ||
        err.payload?.email?.[0] ||
        err.payload?.password?.[0] ||
        err.message ||
        "Login failed. Check your credentials.";
      // SimpleJWT's generic "Given token not valid for any token
      // type" message means we sent a stale Bearer — by the time we
      // see it, api.js has already wiped localStorage. Reword for
      // the user; the underlying state is already fixed.
      const friendly = /Given token not valid/.test(reason)
        ? "Session expired — please sign in again."
        : reason;
      setError(friendly);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="d4-chat login-page" data-theme="light">
      {/* Page-scoped: just style the minimal footer. The page itself
          uses the default d4-chat-scroller scrolling behavior — no
          viewport lock, so taller content / smaller screens scroll
          normally. */}
      <style>{`
        .login-page .login-footer {
          flex: 0 0 auto;
          padding: 0.6rem 1.25rem;
          border-top: 1px solid var(--chat-border, #eee);
          background: var(--chat-bg, #fff);
          color: var(--chat-muted, #666);
          font-size: 0.8rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .login-page .login-footer a {
          color: inherit;
          text-decoration: none;
          font-weight: 600;
        }
        .login-page .login-footer a:hover { text-decoration: underline; }
      `}</style>

      <header className="d4-chat-header">
        <Link to="/" className="d4-chat-brand" title="Back to landing">
          <span className="logo-dot">C</span>
          <span>CarPapi</span>
        </Link>
      </header>

      <main className="d4-chat-scroller">
        <motion.div
          className="d4-chat-empty"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          style={{ maxWidth: 460 }}
        >
          <div className="d4-chat-empty-logo">
            <i className="bi bi-shield-lock-fill"></i>
          </div>
          <h1 className="d4-chat-empty-title">Sign in to CarPapi</h1>
          <p className="d4-chat-empty-sub">
            Welcome back. Sign in to chat with live dealer inventory.
          </p>

          {/* Google */}
          <a
            href={googleLoginUrl(next)}
            style={{
              ...buttonBase,
              marginTop: 18,
              textDecoration: "none",
              background: "#fff",
              color: "#3c4043",
              border: "1px solid #dadce0",
            }}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"
              />
              <path
                fill="#34A853"
                d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"
              />
              <path
                fill="#FBBC05"
                d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.96H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.04l3.007-2.333z"
              />
              <path
                fill="#EA4335"
                d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.892 11.426 0 9 0 5.482 0 2.438 2.017.957 4.96L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z"
              />
            </svg>
            Continue with Google
          </a>

          {/* Email / password */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              margin: "20px 0 14px",
              color: "#666",
              fontSize: 13,
            }}
          >
            <hr style={{ flex: 1, border: 0, borderTop: "1px solid #e5e5e5" }} />
            or
            <hr style={{ flex: 1, border: 0, borderTop: "1px solid #e5e5e5" }} />
          </div>

          <form onSubmit={onSubmit} style={{ width: "100%" }} autoComplete="on">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              autoFocus
              disabled={busy}
              required
              aria-label="Email"
              style={inputBaseStyle}
            />
            <div style={{ height: 10 }} />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              disabled={busy}
              required
              aria-label="Password"
              style={inputBaseStyle}
            />

            {error && (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 14px",
                  borderRadius: 10,
                  background: "rgba(220, 38, 38, 0.08)",
                  color: "#b91c1c",
                  fontSize: 14,
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!email.trim() || !password || busy}
              style={{
                ...buttonBase,
                background: "#111",
                color: "#fff",
                opacity: !email.trim() || !password || busy ? 0.55 : 1,
              }}
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </motion.div>
      </main>

      <footer className="login-footer">
        <span>© {new Date().getFullYear()} CarPapi</span>
        <Link to={`/register?next=${encodeURIComponent(next)}`}>
          Create account
        </Link>
      </footer>
    </div>
  );
}
