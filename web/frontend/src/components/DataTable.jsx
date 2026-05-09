import { useEffect, useState } from "react";
import { getJson } from "../api.js";

/**
 * Generic paginated/searchable table backed by a DRF list endpoint.
 *
 * columns: [{ key, label, render? }]
 */
export default function DataTable({
  title,
  endpoint,
  columns,
  searchable = true,
  initialOrdering,
}) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [data, setData] = useState({ count: 0, results: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getJson(endpoint, {
      page,
      search: searchable ? search : undefined,
      ordering: initialOrdering,
    })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [endpoint, page, search, initialOrdering, searchable]);

  const rows = data.results || data;
  const total = data.count ?? rows.length;
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="d4-card">
      <div className="d4-card-header">
        <h2 className="d4-card-title">{title}</h2>
        {searchable && (
          <div className="d4-search">
            <input
              type="search"
              placeholder="Search…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="d4-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={columns.length} className="d4-empty">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && error && (
              <tr>
                <td colSpan={columns.length} className="d4-empty">
                  Error: {error}
                </td>
              </tr>
            )}
            {!loading && !error && rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="d4-empty">
                  No rows.
                </td>
              </tr>
            )}
            {!loading &&
              !error &&
              rows.map((row, i) => (
                <tr key={row.id || row.slug || i}>
                  {columns.map((c) => (
                    <td key={c.key}>
                      {c.render ? c.render(row) : row[c.key] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="d4-pagination">
        <span>
          {total.toLocaleString()} total · page {page} of {pageCount}
        </span>
        <button onClick={() => setPage(1)} disabled={page <= 1}>
          «
        </button>
        <button onClick={() => setPage((p) => p - 1)} disabled={page <= 1}>
          ‹
        </button>
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={page >= pageCount}
        >
          ›
        </button>
        <button onClick={() => setPage(pageCount)} disabled={page >= pageCount}>
          »
        </button>
      </div>
    </div>
  );
}
