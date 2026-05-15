/**
 * /admin/verify — second step of staff login.
 *
 * Reached only as a redirect from /login after the backend returned a
 * `challenge: "admin_otp"` response (i.e. the user passed the
 * password check AND is_staff is true). The challenge details (token,
 * masked destination, expiry, channel) ride in router state.
 *
 * User flow:
 *   1. Page renders "We sent a code to <hint>" + a 6-digit input.
 *   2. User types the code → POST /api/admin-otp/verify/ with
 *      `{ challenge_token, code }`. Backend returns the usual
 *      `{ access, refresh, user }` JWT payload on success.
 *   3. We hand the JWT to api.setAuth + bounce to /dashboard.
 *
 * "Resend" button issues a POST to /api/admin-otp/resend/ to mint a
 * fresh challenge if the SMS / email got lost. The new challenge_token
 * replaces the old one in component state.
 *
 * Visual language matches /login — same `d4-chat` shell, same form
 * primitives, so the user feels like one flow.
 */
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { postJson, setAuth } from "../api.js";
import { useAuth } from "../auth.jsx";

const inputBox = {
  width: "100%",
  padding: "14px 16px",
  borderRadius: 12,
  border: "1px solid rgba(0,0,0,0.15)",
  fontSize: 24,
  fontWeight: 600,
  letterSpacing: 6,
  background: "#fff",
  color: "#111",
  outline: "none",
  textAlign: "center",
  fontFeatureSettings: "'tnum' 1",
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
};

export default function AdminVerify() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn } = useAuth();

  // Challenge state ships in via router state. If someone deep-links
  // here without a challenge, bounce them to /login.
  const initial = location.state || {};
  const [challengeToken, setChallengeToken] = useState(
    initial.challenge_token || "",
  );
  const [hint, setHint] = useState(initial.destination_hint || "");
  const [channel, setChannel] = useState(initial.channel || "email");
  const [expiresAt, setExpiresAt] = useState(initial.expires_at || null);
  const next = initial.next || "/dashboard";

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);

  const inputRef = useRef(null);

  // Without a challenge token, the page is meaningless.
  useEffect(() => {
    if (!challengeToken) {
      navigate("/login", { replace: true });
    }
  }, [challengeToken, navigate]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const channelLabel = {
    whatsapp: `WhatsApp to ${hint || "your phone"}`,
    sms: `SMS to ${hint || "your phone"}`,
    email: `email to ${hint || "your inbox"}`,
    log: "the dev log (no production channel wired)",
  }[channel] || "your registered channel";

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code.trim()) || busy) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await postJson("/admin-otp/verify/", {
        challenge_token: challengeToken,
        code: code.trim(),
      });
      const auth = { access: res.access, refresh: res.refresh, user: res.user };
      setAuth(auth);
      signIn(auth);
      navigate(next, { replace: true });
    } catch (err) {
      const reason =
        (err.payload && err.payload.detail) || err.message || "Code rejected";
      setError(
        {
          bad_code: "Wrong code. Try again.",
          expired: "Code expired. Resend a new one.",
          already_used: "This code was already used. Resend a new one.",
          too_many_attempts: "Too many wrong attempts. Resend a new one.",
          unknown_challenge: "Session lost. Start over from sign-in.",
        }[reason] || reason,
      );
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    setError(null);
    setInfo(null);
    try {
      const res = await postJson("/admin-otp/resend/", {
        challenge_token: challengeToken,
      });
      setChallengeToken(res.challenge_token);
      setHint(res.destination_hint);
      setChannel(res.channel);
      setExpiresAt(res.expires_at);
      setCode("");
      setInfo("New code sent.");
    } catch (err) {
      const reason = (err.payload && err.payload.detail) || err.message;
      if (reason === "unknown_challenge") {
        navigate("/login", { replace: true });
      } else {
        setError("Couldn't send a new code: " + reason);
      }
    }
  };

  return (
    <div className="d4-chat" data-theme="light">
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
            <i className="bi bi-shield-shaded"></i>
          </div>
          <h1 className="d4-chat-empty-title">One more step</h1>
          <p className="d4-chat-empty-sub">
            For admin access, we just sent a 6-digit code via{" "}
            <strong>{channelLabel}</strong>. Enter it below.
          </p>

          <form onSubmit={onSubmit} style={{ width: "100%", marginTop: 18 }}>
            <input
              ref={inputRef}
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              placeholder="••••••"
              autoComplete="one-time-code"
              disabled={busy}
              aria-label="Six-digit code"
              style={inputBox}
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

            {info && !error && (
              <div
                style={{
                  marginTop: 12,
                  padding: "10px 14px",
                  borderRadius: 10,
                  background: "rgba(16, 185, 129, 0.10)",
                  color: "#047857",
                  fontSize: 14,
                }}
              >
                {info}
              </div>
            )}

            <button
              type="submit"
              disabled={!/^\d{6}$/.test(code) || busy}
              style={{
                ...buttonBase,
                background: "#111",
                color: "#fff",
                opacity: !/^\d{6}$/.test(code) || busy ? 0.55 : 1,
              }}
            >
              {busy ? "Verifying…" : "Verify and continue"}
            </button>
          </form>

          <div
            style={{
              marginTop: 18,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              width: "100%",
              fontSize: 14,
              color: "#666",
            }}
          >
            <button
              type="button"
              onClick={onResend}
              style={{
                background: "transparent",
                border: "none",
                color: "#111",
                fontWeight: 600,
                cursor: "pointer",
                padding: 0,
              }}
            >
              Resend code
            </button>
            <Link
              to="/login"
              style={{ color: "#666", textDecoration: "underline" }}
            >
              Back to sign in
            </Link>
          </div>

          {channel === "log" && (
            <div
              style={{
                marginTop: 20,
                padding: 12,
                borderRadius: 10,
                background: "rgba(245, 158, 11, 0.08)",
                color: "#92400e",
                fontSize: 13,
                textAlign: "left",
              }}
            >
              <strong>Dev mode:</strong> no SMS / email channel is
              wired. The code is in the Django log — check the backend
              console.
            </div>
          )}
        </motion.div>
      </main>
    </div>
  );
}
