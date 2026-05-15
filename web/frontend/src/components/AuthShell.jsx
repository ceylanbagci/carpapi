import { Link } from "react-router-dom";

/**
 * Two-pane shell for login / signup / forgot / reset pages.
 * Left: brand panel with tagline + decorative gradient.
 * Right: the form (children).
 */
export default function AuthShell({
  eyebrow,
  title,
  subtitle,
  footerLinks,
  children,
}) {
  return (
    <div className="d4-auth">
      <aside className="d4-auth-brand">
        {/* <a> (not Link) so clicking goes to CloudFront's landing.html.
            See PublicChrome for the why. */}
        <a href="/" className="d4-auth-brand-logo">
          <span className="logo-dot">C</span>
          <span>CarPapi</span>
        </a>
        <div className="d4-auth-brand-body">
          <div className="d4-auth-brand-eyebrow">Live dealer inventory</div>
          <h2 className="d4-auth-brand-title">
            Real cars,
            <br />
            from real dealers,
            <br />
            in real time.
          </h2>
          <p className="d4-auth-brand-sub">
            Sign in to save searches, get price-drop alerts, and chat with
            your own inventory assistant.
          </p>
          <ul className="d4-auth-brand-points">
            <li>
              <i className="bi bi-check-circle-fill"></i>
              Searchable across every listing on the lot
            </li>
            <li>
              <i className="bi bi-check-circle-fill"></i>
              Window-sticker MSRP + factory specs
            </li>
            <li>
              <i className="bi bi-check-circle-fill"></i>
              Direct links to the dealer's listing — no middleman
            </li>
          </ul>
        </div>
        <div className="d4-auth-brand-foot">
          © {new Date().getFullYear()} CarPapi
        </div>
      </aside>

      <main className="d4-auth-pane">
        <div className="d4-auth-pane-inner">
          <header className="d4-auth-header">
            {eyebrow && <div className="d4-auth-eyebrow">{eyebrow}</div>}
            <h1 className="d4-auth-title">{title}</h1>
            {subtitle && <p className="d4-auth-sub">{subtitle}</p>}
          </header>

          {children}

          {footerLinks && footerLinks.length > 0 && (
            <footer className="d4-auth-footer">
              {footerLinks.map((l, i) => (
                <span key={i} className="d4-auth-footer-link">
                  {l.text}{" "}
                  {l.to ? (
                    <Link to={l.to}>{l.label}</Link>
                  ) : (
                    <a href={l.href}>{l.label}</a>
                  )}
                </span>
              ))}
            </footer>
          )}
        </div>
      </main>
    </div>
  );
}
