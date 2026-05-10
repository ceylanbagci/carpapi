import { useLocation } from "react-router-dom";

const TITLES = {
  "/": "Dashboard",
  "/cars": "Cars",
  "/dealers": "Dealers",
  "/listings": "Listings",
  "/makes": "Makes",
  "/models": "Models",
};

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
      <div className="d4-header-actions">
        <span>
          <i className="bi bi-database-check me-1"></i>
          carpapi @ localhost:5433
        </span>
      </div>
    </header>
  );
}
