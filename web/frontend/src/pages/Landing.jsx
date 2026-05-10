import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getJson } from "../api.js";

const FEATURED_MAKE_SLUGS = [
  "ford",
  "honda",
  "toyota",
  "chevrolet",
  "bmw",
  "audi",
  "mercedes-benz",
  "tesla",
  "lexus",
  "porsche",
  "subaru",
  "hyundai",
];

const FEATURE_CARDS = [
  {
    icon: "bi-broadcast-pin",
    title: "Live inventory",
    body: "Listings refresh continuously from the dealer network — what you see is what's on the lot right now.",
  },
  {
    icon: "bi-tags",
    title: "Every major make",
    body: "From Acura to Volvo, with USA homepages and brand identification built in. Filter by make, model, year, or price range.",
  },
  {
    icon: "bi-shop",
    title: "Local dealers",
    body: "Sourced directly from dealer sites — no aggregator middleman, no stale data, no hidden listings.",
  },
];

export default function Landing() {
  const [stats, setStats] = useState(null);
  const [topMakes, setTopMakes] = useState([]);

  useEffect(() => {
    getJson("/stats/").then(setStats).catch(() => {});
    getJson("/makes/", { page_size: 100 })
      .then((d) => {
        const all = d.results || [];
        const bySlug = Object.fromEntries(all.map((m) => [m.slug, m]));
        setTopMakes(
          FEATURED_MAKE_SLUGS.map((s) => bySlug[s]).filter(Boolean),
        );
      })
      .catch(() => {});
  }, []);

  const fmt = (n) => (n == null ? "…" : n.toLocaleString());

  return (
    <div className="d4-landing">
      <header className="d4-landing-nav">
        <Link to="/" className="d4-landing-brand">
          <span className="logo-dot">C</span>
          <span>CarPapi</span>
        </Link>
        <nav className="d4-landing-links">
          <Link to="/cars">Cars</Link>
          <Link to="/dealers">Dealers</Link>
          <Link to="/makes">Makes</Link>
          <Link to="/listings">Listings</Link>
          <Link to="/dashboard" className="btn btn-primary btn-sm">
            Open Dashboard
          </Link>
        </nav>
      </header>

      <section className="d4-hero">
        <div className="d4-hero-inner">
          <div className="d4-hero-eyebrow">Live dealer inventory · New Jersey</div>
          <h1 className="d4-hero-title">
            Find the right car,
            <br />
            straight from the dealer.
          </h1>
          <p className="d4-hero-sub">
            CarPapi indexes inventory across {fmt(stats?.dealers)} dealers and{" "}
            {fmt(stats?.makes)} makes — searchable, filterable, and updated as
            the lot changes.
          </p>
          <div className="d4-hero-ctas">
            <Link to="/cars" className="btn btn-primary btn-lg">
              Browse cars
              <i className="bi bi-arrow-right ms-2"></i>
            </Link>
            <Link to="/dashboard" className="btn btn-outline-light btn-lg">
              Open dashboard
            </Link>
          </div>

          <div className="d4-hero-stats">
            <Stat label="Listings" value={fmt(stats?.listings)} />
            <Stat label="Cars" value={fmt(stats?.cars)} />
            <Stat label="Dealers" value={fmt(stats?.dealers)} />
            <Stat label="Makes" value={fmt(stats?.makes)} />
            <Stat label="Models" value={fmt(stats?.models)} />
          </div>
        </div>
      </section>

      <section className="d4-section">
        <div className="container">
          <div className="text-center mb-5">
            <div className="d4-eyebrow">Why CarPapi</div>
            <h2 className="d4-h2">Built for people who actually shop.</h2>
          </div>
          <div className="row g-4">
            {FEATURE_CARDS.map((f) => (
              <div className="col-12 col-md-4" key={f.title}>
                <div className="d4-feature">
                  <div className="d4-feature-icon">
                    <i className={`bi ${f.icon}`}></i>
                  </div>
                  <h3 className="h5 mb-2">{f.title}</h3>
                  <p className="text-muted mb-0">{f.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {topMakes.length > 0 && (
        <section className="d4-section d4-section-alt">
          <div className="container">
            <div className="text-center mb-4">
              <div className="d4-eyebrow">Browse by make</div>
              <h2 className="d4-h2">All the brands you'd expect.</h2>
            </div>
            <div className="d4-makes-grid">
              {topMakes.map((m) => (
                <Link
                  key={m.slug}
                  to={`/listings?make=${encodeURIComponent(m.make)}`}
                  className="d4-make-tile"
                  title={`${m.make} · ${m.listing_count} listings`}
                >
                  {m.logo_url && (
                    <img
                      src={m.logo_url}
                      alt={`${m.make} logo`}
                      width="56"
                      height="56"
                      loading="lazy"
                    />
                  )}
                  <span className="d4-make-name">{m.make}</span>
                  <span className="d4-make-count">
                    {m.listing_count.toLocaleString()} listings
                  </span>
                </Link>
              ))}
            </div>
            <div className="text-center mt-4">
              <Link to="/makes" className="btn btn-outline-primary">
                See all makes
                <i className="bi bi-arrow-right ms-2"></i>
              </Link>
            </div>
          </div>
        </section>
      )}

      <section className="d4-cta">
        <div className="container">
          <div className="d4-cta-card">
            <div>
              <h2 className="d4-h2 mb-2">Ready to dig in?</h2>
              <p className="text-muted mb-0">
                The dashboard has every filter, every column sortable, and
                every dealer on a single screen.
              </p>
            </div>
            <Link to="/dashboard" className="btn btn-primary btn-lg">
              Open Dashboard
              <i className="bi bi-arrow-right ms-2"></i>
            </Link>
          </div>
        </div>
      </section>

      <footer className="d4-landing-footer">
        <div className="container d-flex justify-content-between align-items-center flex-wrap gap-2">
          <span>© {new Date().getFullYear()} CarPapi</span>
          <div className="d-flex gap-3">
            <Link to="/dashboard">Dashboard</Link>
            <a
              href="https://github.com/ceylanbagci/carpapi"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="d4-hero-stat">
      <div className="d4-hero-stat-value">{value}</div>
      <div className="d4-hero-stat-label">{label}</div>
    </div>
  );
}
