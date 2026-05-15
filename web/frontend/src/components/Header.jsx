import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

const TITLES = {
  "/dashboard": "Dashboard",
  "/cars": "Cars",
  "/dealers": "Dealers",
  "/listings": "Listings",
  "/makes": "Makes",
  "/models": "Models",
  "/agents": "Fleet Console",
};

export default function Header({ onToggleSidebar }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const title = TITLES[pathname] || "CarPapi";

  const onSignOut = async () => {
    await signOut();
    navigate("/login", { replace: true });
  };

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
      <div className="d4-header-actions" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Link to="/chat" className="btn btn-light btn-sm" title="Open chat">
          <i className="bi bi-chat-dots me-1"></i>
          Chat
        </Link>
        <Link to="/settings" className="btn btn-light btn-sm" title="User settings">
          <i className="bi bi-person-gear me-1"></i>
          Settings
        </Link>
        {user && (
          <button
            type="button"
            className="btn btn-light btn-sm"
            onClick={onSignOut}
            title={`Signed in as ${user.email}`}
          >
            <i className="bi bi-box-arrow-right me-1"></i>
            Sign out
          </button>
        )}
      </div>
    </header>
  );
}
