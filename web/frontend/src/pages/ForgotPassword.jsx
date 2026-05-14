import { useState } from "react";
import { Link } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import { requestPasswordReset } from "../data/mockAuth.js";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [resetUrl, setResetUrl] = useState(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (e) => {
    e.preventDefault();
    setBusy(true);
    const res = requestPasswordReset({ email });
    setBusy(false);
    setSent(true);
    // In a real backend the token would land in the user's email. For
    // the UI mock we expose the would-be reset link so the demo flow
    // is testable end-to-end.
    if (res.token) {
      setResetUrl(`/reset-password?token=${res.token}`);
    }
  };

  return (
    <AuthShell
      eyebrow="Forgot password"
      title="Reset your password"
      subtitle="Enter the email tied to your CarPapi account. We'll send you a link to choose a new password."
      footerLinks={[
        { text: "Remembered it?", label: "Sign in", to: "/login" },
        { text: "No account?", label: "Create one", to: "/signup" },
      ]}
    >
      {!sent ? (
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
          <button type="submit" className="d4-form-submit" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </button>
        </form>
      ) : (
        <div className="d4-auth-success">
          <div className="d4-auth-success-icon">
            <i className="bi bi-envelope-check"></i>
          </div>
          <h2>Check your email</h2>
          <p>
            If an account exists for <strong>{email}</strong>, a reset link is
            on its way. The link expires in 1 hour.
          </p>
          {resetUrl && (
            <div className="d4-mock-note">
              <strong>Demo mode:</strong> no real email is sent — your reset
              link is{" "}
              <Link to={resetUrl}>
                <code>{resetUrl}</code>
              </Link>
              .
            </div>
          )}
          <Link to="/login" className="d4-form-submit d4-form-submit-ghost">
            Back to sign in
          </Link>
        </div>
      )}
    </AuthShell>
  );
}
