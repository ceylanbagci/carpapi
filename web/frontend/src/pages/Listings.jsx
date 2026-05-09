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
  { key: "price_amount", label: "Price", render: fmtPrice },
  {
    key: "city",
    label: "Location",
    render: (r) => [r.city, r.region].filter(Boolean).join(", ") || "—",
  },
  { key: "source_id", label: "Source" },
];

export default function Listings() {
  return (
    <DataTable
      title="Listings"
      endpoint="/listings/"
      columns={columns}
      initialOrdering="-scraped_at"
    />
  );
}
