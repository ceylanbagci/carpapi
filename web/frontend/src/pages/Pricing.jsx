import { useState } from "react";
import { Link } from "react-router-dom";
import { currentUser } from "../data/mockAuth.js";
import { PublicTopBar, PublicFooter } from "../components/PublicChrome.jsx";

// Pricing is presentation-only — no payment integration yet.
// CTAs route to /signup?plan=<id> (or /account if already signed in).

const PLANS = [
  {
    id: "free",
    name: "Free",
    tagline: "Kick the tires.",
    price: { monthly: 0, yearly: 0 },
    perks: [
      "Search every public listing",
      "20 chat queries per day",
      "Compare up to 3 cars side-by-side",
      "Email digest, weekly",
    ],
    limits: ["No API access", "No saved alerts"],
    cta: "Start free",
    highlight: false,
  },
  {
    id: "pro",
    name: "Pro",
    tagline: "Daily shoppers and enthusiasts.",
    price: { monthly: 12, yearly: 9 },
    perks: [
      "Everything in Free",
      "Unlimited chat queries",
      "Saved searches + price-drop alerts",
      "Window-sticker MSRP + factory specs",
      "Compare up to 10 cars",
      "Priority enrichment for your saved VINs",
    ],
    limits: [],
    cta: "Try Pro free for 14 days",
    highlight: true,
    badge: "Most popular",
  },
  {
    id: "team",
    name: "Team",
    tagline: "Dealers, brokers, and analysts.",
    price: { monthly: 49, yearly: 39 },
    perks: [
      "Everything in Pro",
      "Up to 10 seats",
      "API access (50k calls / mo)",
      "CSV / Webhook exports",
      "Per-seat saved searches",
      "Slack alert delivery",
    ],
    limits: [],
    cta: "Talk to us",
    highlight: false,
  },
];

const FEATURE_MATRIX = [
  { label: "Live dealer inventory search", free: true, pro: true, team: true },
  { label: "Chat assistant (LLM)", free: "20/day", pro: "Unlimited", team: "Unlimited" },
  { label: "Side-by-side comparison", free: "3 cars", pro: "10 cars", team: "Unlimited" },
  { label: "Window sticker (MSRP / options / MPG)", free: false, pro: true, team: true },
  { label: "Maker-site spec validation", free: false, pro: true, team: true },
  { label: "Saved searches", free: false, pro: true, team: true },
  { label: "Price-drop alerts (email)", free: false, pro: true, team: true },
  { label: "Slack alert delivery", free: false, pro: false, team: true },
  { label: "API access", free: false, pro: false, team: "50k / mo" },
  { label: "CSV + webhook exports", free: false, pro: false, team: true },
  { label: "Team seats", free: "1", pro: "1", team: "10" },
  { label: "Support", free: "Community", pro: "Email", team: "Priority email + Slack" },
];

const FAQ = [
  {
    q: "Do you take a credit card today?",
    a: "No — the pricing page is here so the product surface is complete, but there's no payment integration yet. Plans pick how Pro/Team users behave inside the app once auth ships.",
  },
  {
    q: "Can I switch plans later?",
    a: "Yes. Plans are not contracts; you can upgrade or downgrade any time from the Account page.",
  },
  {
    q: "Where does the data come from?",
    a: "Live dealer inventory + manufacturer model pages + Monroney window stickers, indexed continuously. Read more in the technical docs.",
  },
  {
    q: "Will my chat history be private?",
    a: "Yes. Conversations are tied to your account; they're never used to train models or shared with dealers.",
  },
];

export default function Pricing() {
  const [billing, setBilling] = useState("yearly"); // "monthly" | "yearly"
  const user = currentUser();

  return (
    <div className="d4-pricing">
      <PublicTopBar />

      <section className="d4-pricing-hero">
        <div className="d4-eyebrow">Simple, honest pricing</div>
        <h1 className="d4-pricing-h1">Pay for what you actually use.</h1>
        <p className="d4-pricing-sub">
          Free covers most shoppers. Pro unlocks alerts and the full
          spec stack. Team is for dealers and analysts who need an API.
        </p>

        <div className="d4-billing-toggle" role="tablist">
          <button
            type="button"
            className={billing === "monthly" ? "active" : ""}
            onClick={() => setBilling("monthly")}
            role="tab"
            aria-selected={billing === "monthly"}
          >
            Monthly
          </button>
          <button
            type="button"
            className={billing === "yearly" ? "active" : ""}
            onClick={() => setBilling("yearly")}
            role="tab"
            aria-selected={billing === "yearly"}
          >
            Yearly
            <span className="d4-billing-save">Save 25%</span>
          </button>
        </div>
      </section>

      <section className="d4-pricing-grid">
        {PLANS.map((p) => {
          const dollars = p.price[billing];
          const isFree = dollars === 0;
          const href = user ? "/account" : `/signup?plan=${p.id}`;
          return (
            <article
              key={p.id}
              className={`d4-plan-card ${p.highlight ? "highlight" : ""}`}
            >
              {p.badge && <div className="d4-plan-badge">{p.badge}</div>}
              <h2 className="d4-plan-card-name">{p.name}</h2>
              <p className="d4-plan-card-tagline">{p.tagline}</p>
              <div className="d4-plan-price">
                <span className="d4-plan-price-currency">$</span>
                <span className="d4-plan-price-amount">{dollars}</span>
                <span className="d4-plan-price-period">
                  {isFree ? "forever" : `/${billing === "yearly" ? "mo, billed yearly" : "mo"}`}
                </span>
              </div>
              <Link to={href} className={`d4-plan-cta ${p.highlight ? "primary" : ""}`}>
                {user ? "Switch to this plan" : p.cta}
              </Link>
              <ul className="d4-plan-perks">
                {p.perks.map((perk) => (
                  <li key={perk}>
                    <i className="bi bi-check2"></i>
                    {perk}
                  </li>
                ))}
                {p.limits.map((limit) => (
                  <li key={limit} className="dim">
                    <i className="bi bi-dash"></i>
                    {limit}
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </section>

      <section className="d4-pricing-matrix">
        <h2 className="d4-h2">Compare features</h2>
        <div className="d4-matrix-wrap">
          <table className="d4-matrix">
            <thead>
              <tr>
                <th></th>
                <th>Free</th>
                <th className="highlight-col">Pro</th>
                <th>Team</th>
              </tr>
            </thead>
            <tbody>
              {FEATURE_MATRIX.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <MatrixCell value={row.free} />
                  <MatrixCell value={row.pro} className="highlight-col" />
                  <MatrixCell value={row.team} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="d4-pricing-faq">
        <h2 className="d4-h2 text-center mb-4">Questions, answered</h2>
        <div className="d4-faq-grid">
          {FAQ.map((f) => (
            <div className="d4-faq-card" key={f.q}>
              <h3>{f.q}</h3>
              <p>{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="d4-pricing-cta">
        <div className="d4-cta-card">
          <div>
            <h2 className="d4-h2 mb-2">Start with Free. Decide later.</h2>
            <p className="text-muted mb-0">
              No credit card. Upgrade only when an alert or the API
              becomes useful.
            </p>
          </div>
          <Link to="/signup" className="btn btn-primary btn-lg">
            Create your account
            <i className="bi bi-arrow-right ms-2"></i>
          </Link>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}

function MatrixCell({ value, className }) {
  let body;
  if (value === true) body = <i className="bi bi-check-lg text-success"></i>;
  else if (value === false || value == null)
    body = <i className="bi bi-dash text-muted"></i>;
  else body = <span className="d4-matrix-value">{value}</span>;
  return <td className={className}>{body}</td>;
}
