/**
 * /register — real-world signup.
 *
 * Fields: email, password (× 1 — Django backend handles password
 * confirmation by accepting password1 == password2; we simplify
 * to one client-side field with a min-length check), full name,
 * phone (optional, E.164), marketing opt-in.
 *
 * On success: api.register() persists JWT auth to localStorage,
 * we bounce to ?next (default /chat).
 */
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { googleLoginUrl, register as apiRegister } from "../api.js";
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

export default function Register() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [marketingOptIn, setMarketingOptIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const next = params.get("next") || "/chat";

  const passwordOk = password.length >= 8;

  const onSubmit = async (e) => {
    e.preventDefault();
    if (busy || !email.trim() || !passwordOk) return;
    setBusy(true);
    setError(null);
    try {
      const auth = await apiRegister({
        email: email.trim(),
        password,
        full_name: fullName.trim(),
        phone: phone.trim() || null,
        marketing_opt_in: marketingOptIn,
      });
      signIn(auth);
      navigate(next, { replace: true });
    } catch (err) {
      // dj-rest-auth returns field-level errors as
      // { email: ["..."], password1: [...], phone: [...] }
      const p = err.payload || {};
      const detail =
        p.detail ||
        p.email?.[0] ||
        p.password1?.[0] ||
        p.password2?.[0] ||
        p.phone?.[0] ||
        p.non_field_errors?.[0] ||
        err.message ||
        "Couldn't create the account. Try again.";
      setError(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="d4-chat" data-theme="light">
      <PublicTopBar />

      <main className="d4-chat-scroller">
        <motion.div
          className="d4-chat-empty"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          style={{ maxWidth: 460 }}
        >
          <div className="d4-chat-empty-logo">
            <i className="bi bi-person-plus-fill"></i>
          </div>
          <h1 className="d4-chat-empty-title">Create your CarPapi account</h1>
          <p className="d4-chat-empty-sub">
            Sign up to chat with live inventory and save the cars you like.
          </p>

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
            Sign up with Google
          </a>

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
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Full name"
              autoComplete="name"
              disabled={busy}
              aria-label="Full name"
              style={inputBaseStyle}
            />
            <div style={{ height: 10 }} />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              disabled={busy}
              required
              aria-label="Email"
              style={inputBaseStyle}
            />
            <div style={{ height: 10 }} />
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone (optional, e.g. +14155551234)"
              autoComplete="tel"
              disabled={busy}
              aria-label="Phone number"
              style={inputBaseStyle}
            />
            <div style={{ height: 10 }} />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password (min 8 characters)"
              autoComplete="new-password"
              disabled={busy}
              required
              minLength={8}
              aria-label="Password"
              style={inputBaseStyle}
            />

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 14,
                fontSize: 14,
                color: "#444",
              }}
            >
              <input
                type="checkbox"
                checked={marketingOptIn}
                onChange={(e) => setMarketingOptIn(e.target.checked)}
                disabled={busy}
              />
              Email me about new listings + dealer promos
            </label>

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
              disabled={!email.trim() || !passwordOk || busy}
              style={{
                ...buttonBase,
                background: "#111",
                color: "#fff",
                opacity: !email.trim() || !passwordOk || busy ? 0.55 : 1,
              }}
            >
              {busy ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p
            style={{
              marginTop: 18,
              fontSize: 14,
              color: "#666",
              textAlign: "center",
            }}
          >
            Already have an account?{" "}
            <Link
              to={`/login?next=${encodeURIComponent(next)}`}
              style={{ color: "#111", fontWeight: 600 }}
            >
              Sign in
            </Link>
          </p>
        </motion.div>
      </main>

      <PublicFooter />
    </div>
  );
}
