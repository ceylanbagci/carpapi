import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { resetPassword } from "../data/mockAuth.js";

export default function ResetPassword() {
  const loc = useLocation();
  const navigate = useNavigate();
  const token = new URLSearchParams(loc.search).get("token") || "";

  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const onSubmit = (e) => {
    e.preventDefault();
    setError(null);
    if (pwd !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setBusy(true);
    const res = resetPassword({ token, newPassword: pwd });
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    setDone(true);
    setTimeout(() => navigate("/login", { replace: true }), 1500);
  };

  if (!token) {
    return (
      <AuthShell
        eyebrow="Reset password"
        title="This reset link is missing a token"
        subtitle="Request a fresh link from the password reset page."
        footerLinks={[{ text: "Need a new link?", label: "Request reset", to: "/forgot-password" }]}
      >
        <Link to="/forgot-password" className="d4-form-submit">
          Request a new link
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      eyebrow="Reset password"
      title="Choose a new password"
      subtitle="Pick something at least 8 characters long. You'll be signed in after."
      footerLinks={[{ text: "Changed your mind?", label: "Back to sign in", to: "/login" }]}
    >
      {done ? (
        <div className="d4-auth-success">
          <div className="d4-auth-success-icon">
            <i className="bi bi-shield-check"></i>
          </div>
          <h2>Password updated</h2>
          <p>Redirecting you to sign in…</p>
        </div>
      ) : (
        <form className="d4-auth-form" onSubmit={onSubmit} noValidate>
          <label className="d4-field">
            <span className="d4-field-label">
              New password
              <span className="d4-field-hint">8 characters minimum</span>
            </span>
            <div className="d4-field-with-toggle">
              <input
                type={showPwd ? "text" : "password"}
                autoComplete="new-password"
                required
                value={pwd}
                onChange={(e) => setPwd(e.target.value)}
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

          <label className="d4-field">
            <span className="d4-field-label">Confirm new password</span>
            <input
              type={showPwd ? "text" : "password"}
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Re-enter the password"
            />
          </label>

          {error && <div className="d4-form-error">{error}</div>}

          <button type="submit" className="d4-form-submit" disabled={busy}>
            {busy ? "Updating…" : "Update password"}
          </button>
        </form>
      )}
    </AuthShell>
  );
}
