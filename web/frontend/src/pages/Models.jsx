import { Link } from "react-router-dom";
import DataTable from "../components/DataTable.jsx";

const columns = [
  { key: "make", label: "Make" },
  { key: "model", label: "Model" },
  {
    key: "count",
    label: "Listings",
    render: (r) =>
      r.count > 0 ? (
        <Link
          to={
            `/listings?make=${encodeURIComponent(r.make)}` +
            `&model=${encodeURIComponent(r.model)}`
          }
          title={`Show ${r.count} ${r.make} ${r.model} listings`}
          style={{ textDecoration: "none" }}
        >
          <span className="d4-pill">{r.count}</span>
        </Link>
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
    />
  );
}
