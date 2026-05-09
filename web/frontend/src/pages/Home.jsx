import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getJson } from "../api.js";

const TILES = [
  { key: "listings", label: "Listings", icon: "bi-list-ul", to: "/listings", tone: "primary" },
  { key: "cars", label: "Distinct Cars", icon: "bi-car-front", to: "/cars", tone: "success" },
  { key: "dealers", label: "Dealers", icon: "bi-shop", to: "/dealers", tone: "warning" },
  { key: "makes", label: "Makes", icon: "bi-tags", to: "/makes", tone: "info" },
  { key: "models", label: "Models", icon: "bi-grid", to: "/models", tone: "secondary" },
  { key: "active_dealers", label: "Active Dealers", icon: "bi-broadcast", to: "/dealers", tone: "success" },
];

export default function Home() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getJson("/stats/")
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="container-fluid p-0">
      <div className="row g-3">
        {TILES.map((t) => (
          <div className="col-12 col-sm-6 col-xl-4" key={t.key}>
            <Link to={t.to} className="text-decoration-none text-reset">
              <div className="d4-card h-100">
                <div className="d4-card-body d-flex align-items-center gap-3">
                  <div
                    className="rounded-3 d-grid place-items-center"
                    style={{
                      width: 48,
                      height: 48,
                      display: "grid",
                      placeItems: "center",
                      background: "rgba(54,153,255,0.1)",
                      color: "#3699FF",
                    }}
                  >
                    <i className={`bi ${t.icon} fs-4`}></i>
                  </div>
                  <div className="d4-stat">
                    <span className="label">{t.label}</span>
                    <span className="value">
                      {error
                        ? "—"
                        : stats?.[t.key] != null
                          ? stats[t.key].toLocaleString()
                          : "…"}
                    </span>
                    <span className="delta">
                      <i className="bi bi-arrow-up-right"></i> live from Postgres
                    </span>
                  </div>
                </div>
              </div>
            </Link>
          </div>
        ))}
      </div>

      {error && (
        <div className="alert alert-warning mt-4 mb-0">
          <strong>API unavailable:</strong> {error}
          <div className="small mt-1">
            Start the Django backend: <code>python manage.py runserver 0.0.0.0:8000</code>
          </div>
        </div>
      )}

      <div className="d4-card mt-4">
        <div className="d4-card-header">
          <h2 className="d4-card-title">Quick links</h2>
        </div>
        <div className="d4-card-body">
          <ul className="list-unstyled m-0">
            <li className="mb-2">
              <i className="bi bi-arrow-right me-2 text-muted"></i>
              <Link to="/listings">Browse all live listings</Link>
            </li>
            <li className="mb-2">
              <i className="bi bi-arrow-right me-2 text-muted"></i>
              <Link to="/dealers">Dealer roster (491+ NJ dealers)</Link>
            </li>
            <li>
              <i className="bi bi-arrow-right me-2 text-muted"></i>
              <Link to="/makes">Makes &amp; models catalog</Link>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
