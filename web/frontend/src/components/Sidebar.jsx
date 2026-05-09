import { NavLink } from "react-router-dom";

const NAV = [
  {
    section: "Dashboard",
    items: [
      { to: "/", label: "Home", icon: "bi-house-door" },
    ],
  },
  {
    section: "Inventory",
    items: [
      { to: "/cars", label: "Cars", icon: "bi-car-front" },
      { to: "/listings", label: "Listings", icon: "bi-list-ul" },
    ],
  },
  {
    section: "Catalog",
    items: [
      { to: "/makes", label: "Makes", icon: "bi-tags" },
      { to: "/models", label: "Models", icon: "bi-grid" },
    ],
  },
  {
    section: "Network",
    items: [
      { to: "/dealers", label: "Dealers", icon: "bi-shop" },
    ],
  },
];

export default function Sidebar({ open }) {
  return (
    <aside className={`d4-sidebar ${open ? "open" : ""}`}>
      <a href="/" className="d4-sidebar-brand">
        <span className="logo-dot">C</span>
        <span>CarPapi</span>
      </a>
      <nav>
        {NAV.map((sec) => (
          <div key={sec.section}>
            <div className="d4-menu-section">{sec.section}</div>
            <ul className="d4-menu">
              {sec.items.map((it) => (
                <li key={it.to}>
                  <NavLink to={it.to} end={it.to === "/"} className="d4-menu-link">
                    <i className={`bi ${it.icon}`}></i>
                    <span>{it.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}
