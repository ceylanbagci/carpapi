import {
  forwardRef,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { respond, SAMPLE_PROMPTS } from "../data/mockChat.js";

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

export default function Chat() {
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

  const send = (raw) => {
    const text = (raw ?? draft).trim();
    if (!text || busy) return;
    setDraft("");
    setBusy(true);

    const userMsg = mkMsg("user", text);
    setMessages((m) => [...m, userMsg]);

    // Simulate the backend "thinking" then return the canned result.
    // 500–900ms gives the typing dots time to feel intentional.
    const delay = 500 + Math.random() * 400;
    setTimeout(() => {
      const reply = respond(text);
      setMessages((m) => [...m, mkMsg("assistant", reply.text, reply.results)]);
      setBusy(false);
    }, delay);
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

  return (
    <div className="d4-chat">
      <header className="d4-chat-header">
        <Link to="/" className="d4-chat-brand" title="Back to landing">
          <span className="logo-dot">C</span>
          <span>CarPapi</span>
        </Link>
        <div className="d4-chat-header-actions">
          <Link to="/dashboard" className="d4-chat-link">
            Dashboard
          </Link>
          {messages.length > 0 && (
            <button
              type="button"
              className="d4-chat-link"
              onClick={clearThread}
              title="Start a new conversation"
            >
              New chat
            </button>
          )}
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
        <i className="bi bi-car-front-fill"></i>
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
        UI preview — responses come from a small mock dataset until the chat
        backend ships.
      </div>
    </form>
  );
});
