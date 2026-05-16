import DataTable from "../components/DataTable.jsx";

// The whole row is clickable — see DataTable's rowHref prop. Clicking
// anywhere on a Models row lands on /listings?make=X&model=Y.
function listingsHref(r) {
  return (
    `/listings?make=${encodeURIComponent(r.make)}` +
    `&model=${encodeURIComponent(r.model)}`
  );
}

const columns = [
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
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
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make" },
  { key: "model", label: "Model", type: "text", placeholder: "Model" },
  { key: "price_min", label: "Min price", type: "number", placeholder: "Price ≥" },
  { key: "price_max", label: "Max price", type: "number", placeholder: "Price ≤" },
];

export default function Models() {
  return (
    <DataTable
      title="Models"
      endpoint="/models/"
      columns={columns}
      filters={filters}
      initialOrdering="-count"
      rowHref={(r) => (r.count > 0 ? listingsHref(r) : null)}
    />
  );
}
