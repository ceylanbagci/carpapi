import DataTable from "../components/DataTable.jsx";

const fmtPrice = (row) => {
  if (row.price_amount == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: row.currency || "USD",
    maximumFractionDigits: 0,
  }).format(row.price_amount);
};

const fmtMileage = (row) =>
  row.mileage == null
    ? "—"
    : `${row.mileage.toLocaleString()} ${row.mileage_unit || ""}`.trim();

const columns = [
  {
    key: "title",
    label: "Title",
    render: (r) => (
      <a href={r.listing_url} target="_blank" rel="noreferrer">
        {r.title}
      </a>
    ),
  },
  { key: "year", label: "Year" },
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  { key: "trim", label: "Trim" },
  { key: "mileage", label: "Mileage", render: fmtMileage },
  { key: "price_amount", label: "Price", render: fmtPrice, sortKey: "price_amount" },
  {
    key: "city",
    label: "Location",
    render: (r) => [r.city, r.region].filter(Boolean).join(", ") || "—",
  },
  { key: "source_id", label: "Source" },
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make (e.g. Ford)" },
  { key: "model", label: "Model", type: "text", placeholder: "Model" },
  { key: "year_min", label: "Year min", type: "number", placeholder: "Year ≥" },
  { key: "year_max", label: "Year max", type: "number", placeholder: "Year ≤" },
  { key: "price_min", label: "Min price", type: "number", placeholder: "Price ≥" },
  { key: "price_max", label: "Max price", type: "number", placeholder: "Price ≤" },
];

export default function Listings() {
  return (
    <DataTable
      title="Listings"
      endpoint="/listings/"
      columns={columns}
      filters={filters}
      initialOrdering="-scraped_at"
    />
  );
}
