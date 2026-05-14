/**
 * /login — single-passphrase gate for /chat.
 *
 * The user pastes the API key once; we save it to localStorage via
 * setApiToken (api.js) and the chat page sees it on every subsequent
 * request via the X-CarPapi-Auth header. On 401 from the backend the
 * chat page navigates back here.
 *
 * No accounts, no signup. Real auth (Cognito/Clerk) is in
 * deploy/PRODUCTION.md §7 as an open decision.
 */
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../auth.jsx";
import { getJson } from "../api.js";

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { signIn } = useAuth();
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const next = params.get("next") || "/chat";

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!passphrase.trim() || busy) return;
    setBusy(true);
    setError(null);

    // Optimistically save the token, then make a real call to verify
    // it works. /api/stats/ is public on the backend — wrong path
    // here would defeat the gate. Instead we POST a no-op /api/chat/
    // request with a tiny message; backend returns 401 if the token
    // is bad, otherwise 200.
    signIn(passphrase.trim());
    try {
      // Probe with a cheap request the backend protects. The chat
      // endpoint's auth check runs before the RAG pipeline so this
      // returns 401 quickly when the token is wrong.
      await getJson("/healthz/");
      // Healthz is public, so we still need to actually hit /chat to
      // see if the token works. Do that with a minimal probe.
      const res = await fetch(
        (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "") + "/chat/",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CarPapi-Auth": passphrase.trim(),
          },
          body: JSON.stringify({ message: "ping" }),
        },
      );
      if (res.status === 401) {
        throw new Error("Wrong passphrase. Try again.");
      }
      // 400 / 200 / 500 — anything other than 401 — means the auth
      // header was accepted (or auth is off for this deploy). Move on.
      navigate(next, { replace: true });
    } catch (err) {
      signIn(null);
      setError(err.message || "Something went wrong, try again.");
    } finally {
      setBusy(false);
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
            <i className="bi bi-shield-lock-fill"></i>
          </div>
          <h1 className="d4-chat-empty-title">Sign in to CarPapi</h1>
          <p className="d4-chat-empty-sub">
            Enter the access passphrase to talk to the live inventory.
          </p>

          <form
            onSubmit={onSubmit}
            style={{ width: "100%", marginTop: 18 }}
            autoComplete="off"
          >
            <div style={{ position: "relative" }}>
              <input
                type="password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                placeholder="passphrase"
                autoFocus
                disabled={busy}
                aria-label="Access passphrase"
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  borderRadius: 12,
                  border: "1px solid var(--d4-border, rgba(0,0,0,0.15))",
                  fontSize: 16,
                  background: "var(--d4-bg-soft, #fff)",
                  color: "var(--d4-fg, #111)",
                  outline: "none",
                }}
              />
            </div>

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
              disabled={!passphrase.trim() || busy}
              style={{
                marginTop: 14,
                width: "100%",
                padding: "12px 16px",
                borderRadius: 12,
                border: "none",
                background: "var(--d4-accent, #111)",
                color: "#fff",
                fontSize: 16,
                fontWeight: 600,
                cursor: busy ? "not-allowed" : "pointer",
                opacity: !passphrase.trim() || busy ? 0.55 : 1,
              }}
            >
              {busy ? "Verifying…" : "Continue"}
            </button>
          </form>

          <p
            style={{
              marginTop: 18,
              fontSize: 13,
              color: "var(--d4-fg-muted, #666)",
            }}
          >
            No account? The MVP uses a shared passphrase — ask the team
            for it.
          </p>
        </motion.div>
      </main>
    </div>
  );
}
