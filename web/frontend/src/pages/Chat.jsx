import {
  forwardRef,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { SAMPLE_PROMPTS } from "../data/mockChat.js";
import { AuthRequiredError, chat as chatApi } from "../api.js";
import CarThumb from "../components/CarThumb.jsx";
import UserMenu from "../components/UserMenu.jsx";

// One message in the thread.
// id: stable key for React
// role: "user" | "assistant" | "thinking"
// text: rendered as the message body
// results: optional list of cars to render below the text (assistant only)
function mkMsg(role, text, results) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    results: results || null,
    at: new Date(),
  };
}

const STORAGE_KEY = "carpapi.chat.thread.v1";
const THEME_KEY = "carpapi.chat.theme.v1";

function initialTheme() {
  if (typeof window === "undefined") return "light";
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* ignore */
  }
  const prefersDark =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

export default function Chat() {
  const navigate = useNavigate();
  // user + signOut are read by <UserMenu/> internally; Chat itself only
  // needs `navigate` (for the AuthRequiredError redirect below).
  const [messages, setMessages] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [theme, setTheme] = useState(initialTheme);
  const scrollerRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      /* ignore quota errors */
    }
  }, [messages]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Persist the user's theme choice. Updating data-theme on the
  // outer .d4-chat element is what swaps the colour tokens.
  useEffect(() => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  // Follow system preference only when the user hasn't pinned a choice
  // yet (no THEME_KEY in storage). Once they toggle, we stop listening.
  useEffect(() => {
    let stored = null;
    try {
      stored = localStorage.getItem(THEME_KEY);
    } catch {
      /* ignore */
    }
    if (stored) return;
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e) => setTheme(e.matches ? "dark" : "light");
    mq.addEventListener?.("change", handler);
    return () => mq.removeEventListener?.("change", handler);
  }, []);

  const send = async (raw) => {
    const text = (raw ?? draft).trim();
    if (!text || busy) return;
    setDraft("");
    setBusy(true);

    const userMsg = mkMsg("user", text);
    setMessages((m) => [...m, userMsg]);

    try {
      // Real RAG call to the backend; api.chat() translates the
      // listings payload into the shape Chat.jsx already renders.
      const reply = await chatApi(text);
      setMessages((m) => [
        ...m,
        mkMsg("assistant", reply.text, reply.results),
      ]);
    } catch (err) {
      // 401 from the backend means the saved token isn't valid — clear
      // it and bounce to /login so the user can re-enter the passphrase.
      if (err instanceof AuthRequiredError) {
        // api.js already wiped the bad token; just bounce.
        navigate("/login?next=/chat", { replace: true });
        return;
      }
      // Surface the error as an assistant message so the user sees
      // *something* in the thread; the backend prose-fallback usually
      // means cards-only with a templated rationale already, so this
      // path is for actual transport-level errors (network down,
      // 5xx from the gateway, etc).
      const msg =
        (err && err.message) ||
        "Sorry — the backend is unreachable right now. Try again in a moment.";
      setMessages((m) => [...m, mkMsg("assistant", `⚠ ${msg}`)]);
    } finally {
      setBusy(false);
    }
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const clearThread = () => {
    setMessages([]);
    localStorage.removeItem(STORAGE_KEY);
    inputRef.current?.focus();
  };

  const isEmpty = messages.length === 0 && !busy;

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  const isDark = theme === "dark";

  return (
    <div className="d4-chat" data-theme={theme}>
      {/* Chat shell header — same layout language as PublicTopBar but
          adapted to the dark/light theme toggle Chat owns. Logo is an
          <a href="/"> (full reload to CloudFront landing.html — the
          React index Route renders a null Landing component, so a
          <Link to="/"> would show a blank page).
          UserMenu replaces the prior Dashboard / signed-in pill /
          Sign-out trio. It exposes the same actions (Chat, Dashboard
          if staff, Settings, Sign out) plus shows the current user's
          initials so the session is always visible top-right. */}
      <header className="d4-chat-header">
        <a href="/" className="d4-chat-brand" title="Back to home">
          <span className="logo-dot">C</span>
          <span>CarPapi</span>
        </a>
        <div className="d4-chat-header-actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="d4-chat-link"
              onClick={clearThread}
              title="Start a new conversation"
            >
              <i className="bi bi-plus-circle me-1"></i>
              New chat
            </button>
          )}
          <button
            type="button"
            className="d4-chat-theme-toggle"
            onClick={toggleTheme}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            aria-pressed={isDark}
          >
            <i className={`bi ${isDark ? "bi-sun" : "bi-moon-stars"}`}></i>
          </button>
          <UserMenu tone={isDark ? "dark" : "light"} />
        </div>
      </header>

      <main className="d4-chat-scroller" ref={scrollerRef}>
        {isEmpty ? (
          <EmptyState onPick={(p) => send(p)} />
        ) : (
          <div className="d4-chat-thread">
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <Message key={m.id} msg={m} />
              ))}
              {busy && <ThinkingDots key="thinking" />}
            </AnimatePresence>
          </div>
        )}
      </main>

      <Composer
        ref={inputRef}
        draft={draft}
        setDraft={setDraft}
        onSubmit={() => send()}
        onKeyDown={onKey}
        busy={busy}
      />
    </div>
  );
}

// --------------------------------------------------------------------- //
// Pieces
// --------------------------------------------------------------------- //

function EmptyState({ onPick }) {
  return (
    <motion.div
      className="d4-chat-empty"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="d4-chat-empty-logo">
        <i className="bi bi-car-front-fill"></i>
      </div>
      <h1 className="d4-chat-empty-title">What are you shopping for?</h1>
      <p className="d4-chat-empty-sub">
        Ask in plain English. CarPapi searches live dealer inventory and
        returns the cars that fit, with a link straight to the listing.
      </p>
      <div className="d4-chat-suggestions">
        {SAMPLE_PROMPTS.map((p) => (
          <button
            key={p}
            type="button"
            className="d4-chat-suggestion"
            onClick={() => onPick(p)}
          >
            {p}
            <i className="bi bi-arrow-up-right"></i>
          </button>
        ))}
      </div>
    </motion.div>
  );
}

function Message({ msg }) {
  return (
    <motion.div
      className={`d4-msg d4-msg-${msg.role}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="d4-msg-avatar">
        {msg.role === "user" ? (
          <i className="bi bi-person-fill"></i>
        ) : (
          <span className="d4-msg-avatar-c">C</span>
        )}
      </div>
      <div className="d4-msg-body">
        <p className="d4-msg-text">{msg.text}</p>
        {msg.results && msg.results.length > 0 && (
          <div className="d4-chat-results">
            {msg.results.map((car) => (
              <CarCard key={car.id} car={car} />
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function CarCard({ car }) {
  const fmtPrice = car.price_amount
    ? new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: car.currency || "USD",
        maximumFractionDigits: 0,
      }).format(car.price_amount)
    : "Call for price";
  const fmtMileage = car.mileage
    ? `${car.mileage.toLocaleString()} ${car.mileage_unit || "mi"}`
    : null;

  return (
    <motion.article
      className="d4-car-card"
      initial={{ opacity: 0, y: 14, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 220, damping: 22 }}
      whileHover={{ y: -3 }}
    >
      <div className="d4-car-card-thumb" aria-hidden="true">
        {/* CarThumb cycles image_url → image_svg_url → bi-car-front-fill icon. */}
        <CarThumb
          imageUrl={car.image_url}
          imageSvgUrl={car.image_svg_url}
          alt={`${car.year || ""} ${car.make || ""} ${car.model || ""}`.trim()}
          width="100%"
          height="100%"
          rounded={0}
        />
      </div>
      <div className="d4-car-card-body">
        <div className="d4-car-card-headline">
          <span className="d4-car-card-year">{car.year}</span>
          <span className="d4-car-card-title">
            {car.make} {car.model}
          </span>
        </div>
        {car.trim && <div className="d4-car-card-trim">{car.trim}</div>}
        <div className="d4-car-card-meta">
          {fmtMileage && <span>{fmtMileage}</span>}
          {car.drivetrain && <span>·</span>}
          {car.drivetrain && <span>{car.drivetrain}</span>}
          {(car.mpg_city || car.mpg_hwy) && <span>·</span>}
          {(car.mpg_city || car.mpg_hwy) && (
            <span>
              {car.mpg_city ?? "?"}/{car.mpg_hwy ?? "?"} mpg
            </span>
          )}
        </div>
        <div className="d4-car-card-foot">
          <span className="d4-car-card-price">{fmtPrice}</span>
          <span className="d4-car-card-dealer">
            <i className="bi bi-shop me-1"></i>
            {car.dealer}
          </span>
        </div>
        <div className="d4-car-card-actions">
          {car.listing_url && (
            <a
              className="d4-car-card-link"
              href={car.listing_url}
              target="_blank"
              rel="noreferrer"
            >
              View listing
              <i className="bi bi-box-arrow-up-right ms-1"></i>
            </a>
          )}
          {car.maker_url && (
            <a
              className="d4-car-card-link secondary"
              href={car.maker_url}
              target="_blank"
              rel="noreferrer"
            >
              On {car.make.toLowerCase()}.com
            </a>
          )}
        </div>
      </div>
    </motion.article>
  );
}

function ThinkingDots() {
  return (
    <motion.div
      className="d4-msg d4-msg-assistant"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
    >
      <div className="d4-msg-avatar">
        <span className="d4-msg-avatar-c">C</span>
      </div>
      <div className="d4-msg-body">
        <span className="d4-chat-dots" aria-label="Thinking">
          <span></span>
          <span></span>
          <span></span>
        </span>
      </div>
    </motion.div>
  );
}

// Composer keeps the textarea grow-with-content without pulling in a lib.

const Composer = forwardRef(function Composer(
  { draft, setDraft, onSubmit, onKeyDown, busy },
  ref,
) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [draft, ref]);

  return (
    <form
      className="d4-chat-composer"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="d4-chat-composer-wrap">
        <textarea
          ref={ref}
          className="d4-chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about live inventory — make, model, price, year…"
          rows={1}
          disabled={busy}
          aria-label="Chat message"
        />
        <button
          type="submit"
          className="d4-chat-send"
          disabled={!draft.trim() || busy}
          aria-label="Send message"
        >
          {busy ? (
            <i className="bi bi-three-dots" />
          ) : (
            <i className="bi bi-arrow-up-circle-fill" />
          )}
        </button>
      </div>
      <div className="d4-chat-footnote">
        Live results from CarPapi's dealer inventory + AI search.
      </div>
    </form>
  );
});
