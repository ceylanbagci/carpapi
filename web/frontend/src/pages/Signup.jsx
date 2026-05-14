import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { signup } from "../data/mockAuth.js";

const PLAN_LABELS = {
  free: "Free",
  pro: "Pro",
  team: "Team",
};

function passwordStrength(pwd) {
  if (!pwd) return 0;
  let s = 0;
  if (pwd.length >= 8) s += 1;
  if (pwd.length >= 12) s += 1;
  if (/[A-Z]/.test(pwd)) s += 1;
  if (/[0-9]/.test(pwd)) s += 1;
  if (/[^A-Za-z0-9]/.test(pwd)) s += 1;
  return Math.min(s, 4);
}

const STRENGTH_LABEL = ["", "Weak", "Fair", "Good", "Strong"];

export default function Signup() {
  const navigate = useNavigate();
  const loc = useLocation();
  const planParam = new URLSearchParams(loc.search).get("plan") || "free";
  const planLabel = PLAN_LABELS[planParam] || PLAN_LABELS.free;

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [agree, setAgree] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const strength = passwordStrength(password);

  const onSubmit = (e) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    if (!agree) {
      setError("You must accept the terms to create an account.");
      return;
    }
    setBusy(true);
    const res = signup({ name, email, password });
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    navigate("/account?welcome=1", { replace: true });
  };

  return (
    <AuthShell
      eyebrow={
        planParam !== "free"
          ? `Signing up for the ${planLabel} plan`
          : "Free to start"
      }
      title="Create your CarPapi account"
      subtitle="Takes ten seconds. No card required."
      footerLinks={[
        { text: "Already have an account?", label: "Sign in", to: "/login" },
        { text: "Want to see the pricing?", label: "Plans", to: "/pricing" },
      ]}
    >
      <form className="d4-auth-form" onSubmit={onSubmit} noValidate>
        <label className="d4-field">
          <span className="d4-field-label">Full name</span>
          <input
            type="text"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jane Driver"
          />
        </label>

        <label className="d4-field">
          <span className="d4-field-label">Work email</span>
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
            <span className="d4-field-hint">8 characters minimum</span>
          </span>
          <div className="d4-field-with-toggle">
            <input
              type={showPwd ? "text" : "password"}
              autoComplete="new-password"
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
          {password && (
            <div className={`d4-strength d4-strength-${strength}`}>
              <span></span>
              <span></span>
              <span></span>
              <span></span>
              <em>{STRENGTH_LABEL[strength]}</em>
            </div>
          )}
        </label>

        <label className="d4-field">
          <span className="d4-field-label">Confirm password</span>
          <input
            type={showPwd ? "text" : "password"}
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Re-enter the password"
          />
        </label>

        <label className="d4-checkbox">
          <input
            type="checkbox"
            checked={agree}
            onChange={(e) => setAgree(e.target.checked)}
          />
          <span>
            I agree to the{" "}
            <a href="#" onClick={(e) => e.preventDefault()}>
              terms
            </a>{" "}
            and{" "}
            <a href="#" onClick={(e) => e.preventDefault()}>
              privacy policy
            </a>
            .
          </span>
        </label>

        {error && <div className="d4-form-error">{error}</div>}

        <button type="submit" className="d4-form-submit" disabled={busy}>
          {busy ? "Creating account…" : `Start with ${planLabel}`}
        </button>

        <div className="d4-form-divider">
          <span>or</span>
        </div>

        <div className="d4-sso-row">
          <button
            type="button"
            className="d4-sso-btn"
            disabled
            title="Coming soon"
          >
            <i className="bi bi-google"></i> Continue with Google
          </button>
        </div>
      </form>
    </AuthShell>
  );
}
