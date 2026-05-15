import { Link, useLocation } from "react-router-dom";
import UserMenu from "./UserMenu.jsx";

const TITLES = {
  "/dashboard": "Dashboard",
  "/cars": "Cars",
  "/dealers": "Dealers",
  "/listings": "Listings",
  "/makes": "Makes",
  "/models": "Models",
  "/agents": "Fleet Console",
};

/**
 * Admin shell top-bar. The Chat + Settings links + the explicit
 * "Sign out" button were replaced by <UserMenu />, which collapses
 * the same actions behind the head-icon dropdown to match the
 * demo4 design pattern and the public landing chrome.
 */
export default function Header({ onToggleSidebar }) {
  const { pathname } = useLocation();
  const title = TITLES[pathname] || "CarPapi";

  return (
    <header className="d4-header">
      <div className="d-flex align-items-center gap-3">
        <button
          type="button"
          className="btn btn-light btn-sm d-md-none"
          onClick={onToggleSidebar}
          aria-label="Toggle menu"
        >
          <i className="bi bi-list"></i>
        </button>
        <h1 className="d4-header-title">{title}</h1>
      </div>
      <div
        className="d4-header-actions"
        style={{ display: "flex", alignItems: "center", gap: 12 }}
      >
        <Link to="/chat" className="btn btn-light btn-sm" title="Open chat">
          <i className="bi bi-chat-dots me-1"></i>
          Chat
        </Link>
        <UserMenu tone="light" />
      </div>
    </header>
  );
}
