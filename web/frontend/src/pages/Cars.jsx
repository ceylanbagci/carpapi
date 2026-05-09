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
  { key: "price_range", label: "Price range", render: fmtRange },
];

export default function Cars() {
  return (
    <DataTable
      title="Cars (distinct year · make · model · trim)"
      endpoint="/cars/"
      columns={columns}
      searchable={false}
    />
  );
}
