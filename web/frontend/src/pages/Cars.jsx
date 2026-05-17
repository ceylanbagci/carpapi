/**
 * /cars — distinct (year · make · model · trim) groups with listing counts.
 *
 * The Listings count is a clickable Link to /listings filtered by the
 * full group key (year + make + model + trim). The Listings page reads
 * the same URL search params and renders exactly those rows. trim=null
 * groups serialize as `trim=` (empty value) — the backend treats that
 * as `trim IS NULL`.
 */
import { Link } from "react-router-dom";
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

/** Builds /listings?year=...&make=...&model=...&trim=... preserving the
 * trim=null convention as an empty `trim=` param so the drill-down
 * matches exactly the same set of rows that produced the count.
 *
 * Both the count cell (Link) and the row-level rowHref use this href —
 * they navigate to the same place, just from different click targets.
 */
function listingsHref(row) {
  const p = new URLSearchParams();
  if (row.year != null) p.set("year", String(row.year));
  if (row.make) p.set("make", row.make);
  if (row.model) p.set("model", row.model);
  // Always include the trim key — empty string carries meaning here
  // (matches trim IS NULL on the backend's _apply_listing_filters).
  p.set("trim", row.trim || "");
  return `/listings?${p.toString()}`;
}

const countCell = (row) => {
  const n = row.count ?? 0;
  const label = `Show ${n.toLocaleString()} listing${n === 1 ? "" : "s"} of `
              + `${row.year || "?"} ${row.make || "?"} ${row.model || "?"}`
              + (row.trim ? ` ${row.trim}` : "");
  if (!n) {
    return (
      <span
        className="d4-pill"
        style={{ fontVariantNumeric: "tabular-nums", color: "#888" }}
      >
        0
      </span>
    );
  }
  return (
    <Link
      to={listingsHref(row)}
      title={label}
      className="d4-pill"
      style={{
        fontVariantNumeric: "tabular-nums",
        fontWeight: 600,
        textDecoration: "none",
        cursor: "pointer",
      }}
    >
      {n.toLocaleString()}
    </Link>
  );
};

const columns = [
  { key: "year", label: "Year" },
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  { key: "trim", label: "Trim" },
  {
    key: "count",
    label: "Listings",
    render: countCell,
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
