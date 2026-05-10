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

const columns = [
  { key: "year", label: "Year" },
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  { key: "trim", label: "Trim" },
  {
    key: "count",
    label: "Listings",
    render: (r) => <span className="d4-pill">{r.count}</span>,
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
    />
  );
}
