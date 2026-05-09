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

export default function Makes() {
  return (
    <DataTable
      title="Makes"
      endpoint="/makes/"
      columns={columns}
      searchable={false}
    />
  );
}
