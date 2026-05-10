import DataTable from "../components/DataTable.jsx";

const logoCell = (r) =>
  r.logo_url ? (
    <img
      src={r.logo_url}
      alt={`${r.make} logo`}
      width="40"
      height="40"
      style={{ borderRadius: 8, display: "block" }}
      loading="lazy"
    />
  ) : (
    <div
      style={{
        width: 40,
        height: 40,
        borderRadius: 8,
        background: "var(--d4-border)",
      }}
    />
  );

const homepageCell = (r) =>
  r.homepage_url ? (
    <a href={r.homepage_url} target="_blank" rel="noreferrer">
      {new URL(r.homepage_url).host.replace(/^www\./, "")}
      <i className="bi bi-box-arrow-up-right ms-1 small"></i>
    </a>
  ) : (
    "—"
  );

const columns = [
  { key: "logo", label: "", sortable: false, render: logoCell },
  { key: "make", label: "Make" },
  {
    key: "homepage_url",
    label: "USA homepage",
    sortable: false,
    render: homepageCell,
  },
  {
    key: "listing_count",
    label: "Listings",
    render: (r) => <span className="d4-pill">{r.listing_count}</span>,
  },
  {
    key: "dealer_count",
    label: "Dealers",
    render: (r) => <span className="d4-pill active">{r.dealer_count}</span>,
  },
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make (exact)" },
  { key: "price_min", label: "Min price", type: "number", placeholder: "Price ≥" },
  { key: "price_max", label: "Max price", type: "number", placeholder: "Price ≤" },
];

export default function Makes() {
  return (
    <DataTable
      title="Makes"
      endpoint="/makes/"
      columns={columns}
      filters={filters}
      initialOrdering="-listing_count"
    />
  );
}
