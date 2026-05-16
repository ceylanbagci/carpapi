import DataTable from "../components/DataTable.jsx";

const fmtRange = (row) => {
  if (row.min_price == null && row.max_price == null) return "—";
  const f = (n) =>
    n == null
      ? "?"
      : new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 0,
        }).format(n);
  return `${f(row.min_price)} – ${f(row.max_price)}`;
};

// Each Cars row is a distinct (year, make, model, trim) tuple. Clicking
// drills into the EXACT slice of /listings — same year, same trim, same
// count as the row shows. The backend honors `trim=__null__` as a
// sentinel for "trim IS NULL" so rows where trim renders as "—" still
// filter exactly. See _apply_listing_filters in web/backend/api/views.py.
function listingsHref(r) {
  const parts = [
    `make=${encodeURIComponent(r.make)}`,
    `model=${encodeURIComponent(r.model)}`,
  ];
  if (r.year) parts.push(`year_min=${r.year}`, `year_max=${r.year}`);
  if (r.trim) parts.push(`trim=${encodeURIComponent(r.trim)}`);
  else        parts.push("trim=__null__");
  return `/listings?${parts.join("&")}`;
}

const columns = [
  { key: "year", label: "Year" },
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  { key: "trim", label: "Trim" },
  {
    key: "count",
    label: "Listings",
    render: (r) =>
      r.count > 0 ? (
        <span className="d4-pill">{r.count}</span>
      ) : (
        <span className="d4-pill" style={{ opacity: 0.5 }}>0</span>
      ),
  },
  {
    key: "min_price",
    label: "Price range",
    render: fmtRange,
    sortKey: "min_price",
  },
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make" },
  { key: "model", label: "Model", type: "text", placeholder: "Model" },
  { key: "year_min", label: "Year min", type: "number", placeholder: "Year ≥" },
  { key: "year_max", label: "Year max", type: "number", placeholder: "Year ≤" },
  { key: "price_min", label: "Min price", type: "number", placeholder: "Price ≥" },
  { key: "price_max", label: "Max price", type: "number", placeholder: "Price ≤" },
];

export default function Cars() {
  return (
    <DataTable
      title="Cars (distinct year · make · model · trim)"
      endpoint="/cars/"
      columns={columns}
      filters={filters}
      rowHref={(r) => (r.count > 0 && r.make && r.model ? listingsHref(r) : null)}
    />
  );
}
