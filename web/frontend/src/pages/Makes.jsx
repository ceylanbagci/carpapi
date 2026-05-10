import DataTable from "../components/DataTable.jsx";

const columns = [
  { key: "make", label: "Make" },
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
