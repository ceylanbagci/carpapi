import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { login, DEMO_CREDENTIALS } from "../data/mockAuth.js";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const loc = useLocation();
  const next = new URLSearchParams(loc.search).get("next") || "/account";

  const onSubmit = (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const res = login({ email, password });
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    navigate(next, { replace: true });
  };

  const useDemo = () => {
    setEmail(DEMO_CREDENTIALS.email);
    setPassword(DEMO_CREDENTIALS.password);
    setError(null);
  };

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to CarPapi"
      subtitle="Use your email and password. We'll keep you signed in on this device."
      footerLinks={[
        { text: "Don't have an account?", label: "Sign up", to: "/signup" },
        { text: "Forgot your password?", label: "Reset it", to: "/forgot-password" },
      ]}
    >
      <form className="d4-auth-form" onSubmit={onSubmit} noValidate>
        <label className="d4-field">
          <span className="d4-field-label">Email</span>
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </label>

        <label className="d4-field">
          <span className="d4-field-label">
            Password
            <Link to="/forgot-password" className="d4-field-link">
              Forgot?
            </Link>
          </span>
          <div className="d4-field-with-toggle">
            <input
              type={showPwd ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
            <button
              type="button"
              className="d4-field-toggle"
              onClick={() => setShowPwd((v) => !v)}
              aria-label={showPwd ? "Hide password" : "Show password"}
            >
              <i className={`bi ${showPwd ? "bi-eye-slash" : "bi-eye"}`}></i>
            </button>
          </div>
        </label>

        <label className="d4-checkbox">
          <input type="checkbox" defaultChecked />
          <span>Stay signed in on this device</span>
        </label>

        {error && <div className="d4-form-error">{error}</div>}

        <button type="submit" className="d4-form-submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <div className="d4-form-divider">
          <span>or</span>
        </div>

        <div className="d4-sso-row">
          <button type="button" className="d4-sso-btn" disabled title="Coming soon">
            <i className="bi bi-google"></i> Google
          </button>
          <button type="button" className="d4-sso-btn" disabled title="Coming soon">
            <i className="bi bi-apple"></i> Apple
          </button>
        </div>

        <button type="button" className="d4-form-demo" onClick={useDemo}>
          Fill demo credentials
        </button>
      </form>
    </AuthShell>
  );
}
