import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MotionConfig, motion } from "framer-motion";
import { getJson } from "../api.js";
import AnimatedCar from "../components/AnimatedCar.jsx";
import AnimatedNumber from "../components/AnimatedNumber.jsx";

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
    body:
      "Listings refresh continuously from the dealer network — what you see is what's on the lot right now.",
  },
  {
    icon: "bi-tags",
    title: "Every major make",
    body:
      "From Acura to Volvo, with USA homepages and brand identification built in. Filter by make, model, year, or price range.",
  },
  {
    icon: "bi-shop",
    title: "Local dealers",
    body:
      "Sourced directly from dealer sites — no aggregator middleman, no stale data, no hidden listings.",
  },
];

// Hero text staggers in *after* the car has settled (~1.0s).
const HERO_DELAY = 1.0;
const HERO_STAGGER = 0.09;

const heroContainer = {
  hidden: {},
  show: { transition: { staggerChildren: HERO_STAGGER, delayChildren: HERO_DELAY } },
};
const heroItem = {
  hidden: { opacity: 0, y: 30 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring", stiffness: 110, damping: 18 },
  },
};

const sectionReveal = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
};

const gridStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07 } },
};
const gridItem = {
  hidden: { opacity: 0, y: 24, scale: 0.96 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 140, damping: 18 },
  },
};

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

  return (
    <MotionConfig reducedMotion="user">
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
          {/* moving road behind everything */}
          <div className="d4-road" aria-hidden="true">
            <motion.div
              className="d4-road-lane"
              initial={{ backgroundPositionX: 0 }}
              animate={{ backgroundPositionX: "-200px" }}
              transition={{ repeat: Infinity, duration: 1.6, ease: "linear" }}
            />
          </div>

          {/* the car drives in */}
          <div className="d4-hero-car">
            <AnimatedCar width={420} />
          </div>

          <motion.div
            className="d4-hero-inner"
            variants={heroContainer}
            initial="hidden"
            animate="show"
          >
            <motion.div variants={heroItem} className="d4-hero-eyebrow">
              Live dealer inventory · New Jersey
            </motion.div>
            <motion.h1 variants={heroItem} className="d4-hero-title">
              Find the right car,
              <br />
              <span className="d4-hero-title-accent">straight from the dealer.</span>
            </motion.h1>
            <motion.p variants={heroItem} className="d4-hero-sub">
              CarPapi indexes inventory across{" "}
              <AnimatedNumber value={stats?.dealers} delay={1.4} duration={1.2} />{" "}
              dealers and{" "}
              <AnimatedNumber value={stats?.makes} delay={1.6} duration={1.2} />{" "}
              makes — searchable, filterable, and updated as the lot changes.
            </motion.p>
            <motion.div variants={heroItem} className="d4-hero-ctas">
              <Link to="/cars" className="btn btn-primary btn-lg">
                Browse cars
                <i className="bi bi-arrow-right ms-2"></i>
              </Link>
              <Link to="/dashboard" className="btn btn-outline-light btn-lg">
                Open dashboard
              </Link>
            </motion.div>

            <motion.div variants={heroItem} className="d4-hero-stats">
              <Stat label="Listings" value={stats?.listings} delay={1.8} />
              <Stat label="Cars" value={stats?.cars} delay={1.9} />
              <Stat label="Dealers" value={stats?.dealers} delay={2.0} />
              <Stat label="Makes" value={stats?.makes} delay={2.1} />
              <Stat label="Models" value={stats?.models} delay={2.2} />
            </motion.div>
          </motion.div>
        </section>

        <motion.section className="d4-section" {...sectionReveal}>
          <div className="container">
            <div className="text-center mb-5">
              <div className="d4-eyebrow">Why CarPapi</div>
              <h2 className="d4-h2">Built for people who actually shop.</h2>
            </div>
            <motion.div
              className="row g-4"
              variants={gridStagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-50px" }}
            >
              {FEATURE_CARDS.map((f) => (
                <motion.div
                  key={f.title}
                  className="col-12 col-md-4"
                  variants={gridItem}
                >
                  <motion.div
                    className="d4-feature"
                    whileHover={{ y: -4 }}
                    transition={{ type: "spring", stiffness: 280, damping: 20 }}
                  >
                    <div className="d4-feature-icon">
                      <i className={`bi ${f.icon}`}></i>
                    </div>
                    <h3 className="h5 mb-2">{f.title}</h3>
                    <p className="text-muted mb-0">{f.body}</p>
                  </motion.div>
                </motion.div>
              ))}
            </motion.div>
          </div>
        </motion.section>

        {topMakes.length > 0 && (
          <motion.section
            className="d4-section d4-section-alt"
            {...sectionReveal}
          >
            <div className="container">
              <div className="text-center mb-4">
                <div className="d4-eyebrow">Browse by make</div>
                <h2 className="d4-h2">All the brands you'd expect.</h2>
              </div>
              <motion.div
                className="d4-makes-grid"
                variants={gridStagger}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-50px" }}
              >
                {topMakes.map((m) => (
                  <motion.div key={m.slug} variants={gridItem}>
                    <motion.div
                      whileHover={{ y: -4, scale: 1.02 }}
                      transition={{ type: "spring", stiffness: 280, damping: 18 }}
                    >
                      <Link
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
                    </motion.div>
                  </motion.div>
                ))}
              </motion.div>
              <div className="text-center mt-4">
                <Link to="/makes" className="btn btn-outline-primary">
                  See all makes
                  <i className="bi bi-arrow-right ms-2"></i>
                </Link>
              </div>
            </div>
          </motion.section>
        )}

        <motion.section className="d4-cta" {...sectionReveal}>
          <div className="container">
            <motion.div
              className="d4-cta-card"
              whileHover={{ y: -2 }}
              transition={{ type: "spring", stiffness: 280, damping: 20 }}
            >
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
            </motion.div>
          </div>
        </motion.section>

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
    </MotionConfig>
  );
}

function Stat({ label, value, delay }) {
  return (
    <div className="d4-hero-stat">
      <div className="d4-hero-stat-value">
        <AnimatedNumber value={value} delay={delay} />
      </div>
      <div className="d4-hero-stat-label">{label}</div>
    </div>
  );
}
