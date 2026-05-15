import DataTable from "../components/DataTable.jsx";

const makesCell = (row) => {
  const m = row.makes_carried;
  if (!m || m.length === 0) return "—";
  if (m.length <= 3) return m.join(", ");
  return `${m.slice(0, 3).join(", ")} +${m.length - 3}`;
};

const carsCell = (row) => {
  const n = row.cars_count ?? 0;
  return (
    <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
      {n.toLocaleString()}
    </span>
  );
};

// "Last Visited" = the most recent scrape we ran against the dealer
// (model field is dealer.last_scraped_at). Show as a relative phrase
// ("3h ago", "2d ago") with the absolute time as a title-tooltip.
const lastVisitedCell = (row) => {
  const iso = row.last_scraped_at;
  if (!iso) return <span style={{ color: "var(--d4-text-muted, #888)" }}>never</span>;
  const t = new Date(iso);
  const diffMs = Date.now() - t.getTime();
  const sec = Math.max(0, Math.floor(diffMs / 1000));
  const min = Math.floor(sec / 60);
  const hr = Math.floor(min / 60);
  const day = Math.floor(hr / 24);
  let phrase;
  if (sec < 60) phrase = `${sec}s ago`;
  else if (min < 60) phrase = `${min}m ago`;
  else if (hr < 24) phrase = `${hr}h ago`;
  else if (day < 30) phrase = `${day}d ago`;
  else phrase = t.toISOString().slice(0, 10);
  return (
    <span title={t.toLocaleString()} style={{ fontVariantNumeric: "tabular-nums" }}>
      {phrase}
    </span>
  );
};

const zipCell = (row) => {
  const z = row.postal_code;
  if (!z) return <span style={{ color: "var(--d4-text-muted, #888)" }}>—</span>;
  return (
    <span style={{ fontVariantNumeric: "tabular-nums", fontFamily: "var(--d4-mono, ui-monospace, SF Mono, monospace)" }}>
      {z}
    </span>
  );
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
  { key: "region", label: "Region" },
  {
    key: "postal_code",
    label: "Zip",
    render: zipCell,
  },
  {
    key: "makes_carried",
    label: "Makes",
    render: makesCell,
    sortable: false,
  },
  {
    key: "cars_count",
    label: "Listings",
    render: carsCell,
  },
  {
    key: "last_scraped_at",
    label: "Last Visited",
    render: lastVisitedCell,
  },
];

const filters = [
  { key: "make", label: "Make", type: "text", placeholder: "Make carried" },
];

export default function Dealers() {
  return (
    <>
      {/* "New separation" — vertical column dividers + zebra stripes so the
          extra columns (Cars / Last Visited) stay scannable. Scoped to the
          Dealers page so other tables aren't affected. */}
      <style>{`
        .dealers-page table.d4-table thead th,
        .dealers-page table.d4-table tbody td {
          border-right: 1px solid var(--d4-border, #eaecef);
        }
        .dealers-page table.d4-table thead th:last-child,
        .dealers-page table.d4-table tbody td:last-child {
          border-right: 0;
        }
        .dealers-page table.d4-table tbody tr:nth-child(even) td {
          background: #fafbfc;
        }
        .dealers-page table.d4-table tbody tr:hover td {
          background: #f1f4f7;
        }
      `}</style>
      <div className="dealers-page">
        <DataTable
          title="Dealers"
          endpoint="/dealers/"
          columns={columns}
          filters={filters}
          initialOrdering="-cars_count"
        />
      </div>
    </>
  );
}
