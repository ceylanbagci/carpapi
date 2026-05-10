import { useEffect, useMemo, useRef, useState } from "react";
import { getJson } from "../api.js";

/**
 * Generic paginated, sortable, filterable table backed by a DRF endpoint.
 *
 * Props:
 *   columns: [{ key, label, render?, sortable? = true, sortKey? = key }]
 *   filters: [{ key, label, type: "text" | "number" | "select",
 *               options?: [{ value, label }], placeholder? }]
 *   searchable: bool — show the global search box
 *   initialOrdering: string — initial DRF-style ordering ("field" / "-field")
 */
export default function DataTable({
  title,
  endpoint,
  columns,
  filters = [],
  searchable = true,
  initialOrdering = "",
}) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [filterValues, setFilterValues] = useState({});
  const [ordering, setOrdering] = useState(initialOrdering);
  const [data, setData] = useState({ count: 0, results: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Debounce text inputs so we don't hammer the API on every keystroke.
  const [committed, setCommitted] = useState({ search: "", filters: {} });
  const debounceRef = useRef();
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setCommitted({ search, filters: filterValues });
      setPage(1);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [search, filterValues]);

  const params = useMemo(() => {
    const p = { page, ordering: ordering || undefined };
    if (committed.search) p.search = committed.search;
    for (const [k, v] of Object.entries(committed.filters)) {
      if (v !== "" && v != null) p[k] = v;
    }
    return p;
  }, [page, ordering, committed]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getJson(endpoint, params)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [endpoint, params]);

  const rows = data.results || data;
  const total = data.count ?? rows.length;
  const pageSize = 25;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const handleSort = (col) => {
    if (col.sortable === false) return;
    const key = col.sortKey || col.key;
    if (ordering === key) setOrdering(`-${key}`);
    else if (ordering === `-${key}`) setOrdering("");
    else setOrdering(key);
    setPage(1);
  };

  const sortIndicator = (col) => {
    if (col.sortable === false) return null;
    const key = col.sortKey || col.key;
    if (ordering === key) return <span className="ms-1 text-primary">↑</span>;
    if (ordering === `-${key}`) return <span className="ms-1 text-primary">↓</span>;
    return <span className="ms-1 text-muted opacity-50">↕</span>;
  };

  const setFilter = (key, value) =>
    setFilterValues((prev) => ({ ...prev, [key]: value }));

  const clearAll = () => {
    setSearch("");
    setFilterValues({});
    setOrdering(initialOrdering);
    setPage(1);
  };

  const hasActiveFilters =
    !!search ||
    Object.values(filterValues).some((v) => v !== "" && v != null) ||
    !!ordering;

  return (
    <div className="d4-card">
      <div className="d4-card-header flex-wrap gap-2">
        <h2 className="d4-card-title">{title}</h2>
        <div className="d4-search d-flex flex-wrap gap-2 align-items-center">
          {searchable && (
            <input
              type="search"
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search"
            />
          )}
          {filters.map((f) => (
            <FilterInput
              key={f.key}
              filter={f}
              value={filterValues[f.key] ?? ""}
              onChange={(v) => setFilter(f.key, v)}
            />
          ))}
          {hasActiveFilters && (
            <button
              type="button"
              className="btn btn-link btn-sm p-0"
              onClick={clearAll}
            >
              Clear
            </button>
          )}
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="d4-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  onClick={() => handleSort(c)}
                  style={{
                    cursor: c.sortable === false ? "default" : "pointer",
                    userSelect: "none",
                  }}
                >
                  {c.label}
                  {sortIndicator(c)}
                </th>
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
                  No rows match your filters.
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

function FilterInput({ filter, value, onChange }) {
  const placeholder = filter.placeholder || filter.label;
  if (filter.type === "select") {
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={filter.label}
        style={{
          border: "1px solid var(--d4-border)",
          borderRadius: 8,
          padding: "0.4rem 0.6rem",
          fontSize: "0.9rem",
          background: "#fafbfc",
          minWidth: 120,
        }}
      >
        <option value="">{`All ${filter.label}`}</option>
        {(filter.options || []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      type={filter.type === "number" ? "number" : "text"}
      inputMode={filter.type === "number" ? "decimal" : undefined}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={filter.label}
      style={{
        border: "1px solid var(--d4-border)",
        borderRadius: 8,
        padding: "0.4rem 0.75rem",
        fontSize: "0.9rem",
        background: "#fafbfc",
        minWidth: filter.type === "number" ? 110 : 140,
      }}
    />
  );
}
