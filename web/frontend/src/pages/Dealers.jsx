import DataTable from "../components/DataTable.jsx";

const statusPill = (row) => (
  <span className={`d4-pill ${row.status || ""}`}>{row.status || "—"}</span>
);

const makesCell = (row) => {
  const m = row.makes_carried;
  if (!m || m.length === 0) return "—";
  if (m.length <= 3) return m.join(", ");
  return `${m.slice(0, 3).join(", ")} +${m.length - 3}`;
};

const columns = [
  {
    key: "name",
    label: "Dealer",
    render: (r) =>
      r.homepage_url ? (
        <a href={r.homepage_url} target="_blank" rel="noreferrer">
          {r.name}
        </a>
      ) : (
        r.name
      ),
  },
  { key: "city", label: "City" },
  { key: "region", label: "Region" },
  { key: "cms", label: "CMS" },
  {
    key: "makes_carried",
    label: "Makes",
    render: makesCell,
    sortable: false,
  },
  { key: "status", label: "Status", render: statusPill },
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make carried" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "active", label: "active" },
      { value: "paused", label: "paused" },
      { value: "blocked", label: "blocked" },
    ],
  },
];

export default function Dealers() {
  return (
    <DataTable
      title="Dealers"
      endpoint="/dealers/"
      columns={columns}
      filters={filters}
      initialOrdering="name"
    />
  );
}
