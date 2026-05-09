import DataTable from "../components/DataTable.jsx";

const columns = [
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  {
    key: "count",
    label: "Listings",
    render: (r) => <span className="d4-pill">{r.count}</span>,
  },
];

export default function Models() {
  return (
    <DataTable
      title="Models"
      endpoint="/models/"
      columns={columns}
      searchable={false}
    />
  );
}
