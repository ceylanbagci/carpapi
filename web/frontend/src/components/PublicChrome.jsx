/**
 * <PublicTopBar /> + <PublicFooter /> — the chrome shared by the
 * non-admin SPA pages (Login, Register, Pricing, Settings, Chat
 * shells). Both render in the light theme used by `d4-chat`.
 *
 * Visually matches `public/landing.html` for continuity — same nav
 * links, same head-icon dropdown when logged in, same multi-column
 * footer. Without this, the SPA's standalone pages each invented
 * their own header pattern (just a `CarPapi` link top-left, nothing
 * else) and there was no footer at all.
 *
 * `<UserMenu />` does the auth-aware swap: logged-out users see
 * "Sign in / Get started"; logged-in users get the head-icon
 * dropdown with Chat / Dashboard / Settings / Sign out.
 */
import { Link } from "react-router-dom";
import UserMenu from "./UserMenu.jsx";

const navLinkStyle = {
  padding: "8px 14px",
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 500,
  color: "#444",
  textDecoration: "none",
  transition: "background 0.15s",
};

function NavLink({ to, children, external = false }) {
  if (external) {
    return (
      <a
        href={to}
        style={navLinkStyle}
        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(0,0,0,0.04)"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
      >
        {children}
      </a>
    );
  }
  return (
    <Link
      to={to}
      style={navLinkStyle}
      onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(0,0,0,0.04)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      {children}
    </Link>
  );
}

export function PublicTopBar() {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 24px",
        background: "#fff",
        borderBottom: "1px solid rgba(0,0,0,0.08)",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <Link
        to="/"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          fontWeight: 700,
          fontSize: 17,
          color: "#111",
          textDecoration: "none",
        }}
      >
        <span
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "#ffd86b",
            color: "#1a1c20",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 800,
            fontSize: 14,
          }}
        >
          C
        </span>
        CarPapi
      </Link>

      <nav style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
        <NavLink to="/chat">Chat</NavLink>
        <NavLink to="/dashboard">Inventory</NavLink>
        <NavLink to="/pricing">Pricing</NavLink>
        <UserMenu tone="light" />
      </nav>
    </header>
  );
}

const colHeading = {
  margin: "0 0 14px",
  fontSize: 12,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "#666",
};

const colList = { listStyle: "none", padding: 0, margin: 0 };
const colItem = { marginBottom: 8 };
const colLink = {
  color: "#444",
  fontSize: 14,
  textDecoration: "none",
};

export function PublicFooter() {
  return (
    <footer
      style={{
        background: "#fafafa",
        borderTop: "1px solid rgba(0,0,0,0.08)",
        marginTop: 64,
      }}
    >
      <div
        style={{
          maxWidth: 1080,
          margin: "0 auto",
          padding: "48px 24px 24px",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr 1fr 1fr",
            gap: 36,
          }}
          className="d4-footer-grid"
        >
          <div>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 12,
              }}
            >
              <span
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 8,
                  background: "#ffd86b",
                  color: "#1a1c20",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 800,
                  fontSize: 14,
                }}
              >
                C
              </span>
              <strong style={{ fontSize: 17, color: "#111" }}>CarPapi</strong>
            </div>
            <p style={{ maxWidth: 280, color: "#666", fontSize: 14, margin: 0 }}>
              Used-car search, in plain English. Real inventory from real
              dealers, refreshed daily.
            </p>
          </div>

          <div>
            <h4 style={colHeading}>Product</h4>
            <ul style={colList}>
              <li style={colItem}><Link style={colLink} to="/chat">Chat search</Link></li>
              <li style={colItem}><Link style={colLink} to="/dashboard">Inventory</Link></li>
              <li style={colItem}><Link style={colLink} to="/pricing">Pricing</Link></li>
              <li style={colItem}><Link style={colLink} to="/register">Get started</Link></li>
            </ul>
          </div>

          <div>
            <h4 style={colHeading}>Company</h4>
            <ul style={colList}>
              <li style={colItem}><a style={colLink} href="mailto:info@carpappi.com">Contact</a></li>
              <li style={colItem}><Link style={colLink} to="/pricing">Pricing</Link></li>
              <li style={colItem}><a style={colLink} href="mailto:marketing@carpappi.com">Press</a></li>
              <li style={colItem}><a style={colLink} href="mailto:admin@carpappi.com">Support</a></li>
            </ul>
          </div>

          <div>
            <h4 style={colHeading}>Legal</h4>
            <ul style={colList}>
              <li style={colItem}><Link style={colLink} to="/legal/privacy">Privacy</Link></li>
              <li style={colItem}><Link style={colLink} to="/legal/terms">Terms</Link></li>
              <li style={colItem}><Link style={colLink} to="/legal/cookies">Cookies</Link></li>
              <li style={colItem}><a style={colLink} href="mailto:admin@carpappi.com">Abuse</a></li>
            </ul>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
            padding: "20px 0 0",
            marginTop: 32,
            borderTop: "1px solid rgba(0,0,0,0.08)",
            fontSize: 13,
            color: "#666",
          }}
        >
          <div>© 2026 CarPapi · used-car search, in plain English.</div>
          <div>
            <a style={{ color: "#666", textDecoration: "none" }} href="mailto:info@carpappi.com">
              info@carpappi.com
            </a>
          </div>
        </div>
      </div>

      {/* Responsive collapse for the footer grid */}
      <style>{`
        @media (max-width: 720px) {
          .d4-footer-grid { grid-template-columns: 1fr 1fr !important; gap: 28px !important; }
          .d4-footer-grid > :first-child { grid-column: span 2; }
        }
      `}</style>
    </footer>
  );
}
