/**
 * /listings (admin shell) — grid of car cards, each with a real
 * thumbnail (CarThumb cycles image_url → image_svg_url → bi-icon).
 *
 * Behaves like the old DataTable: paginated, sortable (a few common
 * sort keys via a dropdown), filterable via the inline filter bar.
 * Hits the same `/api/listings/` endpoint and same query-string
 * convention (`page`, `ordering`, plus filter keys).
 *
 * The "beautiful" upgrade is purely visual — same data, same API.
 * Cards show: thumbnail · year + make + model + trim · mileage · price
 * · dealer · scrape date · clickable open-in-new-tab to the dealer page.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getJson } from "../api.js";
import CarThumb from "../components/CarThumb.jsx";

// Keys the page recognizes from the URL query string. The drill-down
// from /cars sends year + make + model + trim; the drill-down from
// /dealers sends source_id; everything else is filter-bar input.
const URL_FILTER_KEYS = [
  "make", "model", "year", "year_min", "year_max",
  "price_min", "price_max", "trim", "source_id",
];

// Pretty labels for the active-filter chips at the top of the grid.
const FILTER_CHIP_LABEL = {
  make:      "Make",
  model:     "Model",
  year:      "Year",
  year_min:  "Year ≥",
  year_max:  "Year ≤",
  price_min: "Price ≥",
  price_max: "Price ≤",
  trim:      "Trim",
  source_id: "Dealer",
};

const fmtPrice = (row) => {
  if (row.price_amount == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: row.currency || "USD",
    maximumFractionDigits: 0,
  }).format(row.price_amount);
};

const fmtMileage = (row) =>
  row.mileage == null
    ? null
    : `${row.mileage.toLocaleString()} ${row.mileage_unit || "mi"}`.trim();

const SORTS = [
  { value: "-scraped_at", label: "Newest first" },
  { value: "scraped_at", label: "Oldest first" },
  { value: "price_amount", label: "Price ↑" },
  { value: "-price_amount", label: "Price ↓" },
  { value: "-year", label: "Year ↓" },
  { value: "year", label: "Year ↑" },
];

const inputStyle = {
  padding: "8px 12px",
  borderRadius: 10,
  border: "1px solid rgba(0,0,0,0.12)",
  fontSize: 14,
  background: "#fff",
  color: "#111",
  outline: "none",
};

export default function Listings() {
  // The URL is the source of truth for drill-down filters (year, make,
  // model, trim, source_id). The filter bar is a *view* into the same
  // state — typing into a filter box updates the URL via setSearchParams
  // which then flows back through this useState. That way a drill-down
  // from /cars or /dealers shows up as removable chips and the URL is
  // shareable.
  const [searchParams, setSearchParams] = useSearchParams();

  const initialFromUrl = () => {
    const out = {};
    for (const k of URL_FILTER_KEYS) {
      // `trim` is special: an empty value means "trim IS NULL" so we
      // must preserve it even when the value is "".
      if (k === "trim" && searchParams.has("trim")) {
        out.trim = searchParams.get("trim") || "";
      } else if (searchParams.has(k)) {
        const v = searchParams.get(k);
        if (v !== "" && v != null) out[k] = v;
      }
    }
    return out;
  };

  const [page, setPage] = useState(1);
  const [ordering, setOrdering] = useState("-scraped_at");
  const [filters, setFilters] = useState(initialFromUrl);
  const [committed, setCommitted] = useState(initialFromUrl);
  const debounceRef = useRef();

  const [data, setData] = useState({ count: 0, results: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setCommitted(filters);
      setPage(1);
      // Reflect the active filters in the URL so a refresh / share
      // preserves them. Empty-string trim is meaningful (matches
      // trim IS NULL) and survives the trip.
      const next = new URLSearchParams();
      for (const k of URL_FILTER_KEYS) {
        if (k === "trim" && filters.trim !== undefined) {
          next.set("trim", filters.trim || "");
        } else if (filters[k] !== "" && filters[k] != null) {
          next.set(k, String(filters[k]));
        }
      }
      setSearchParams(next, { replace: true });
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [filters, setSearchParams]);

  const removeFilter = (key) => {
    const next = { ...filters };
    delete next[key];
    setFilters(next);
  };
  const clearAllFilters = () => setFilters({});

  const params = useMemo(() => {
    const p = { page, ordering };
    for (const [k, v] of Object.entries(committed)) {
      if (v !== "" && v != null) p[k] = v;
    }
    return p;
  }, [page, ordering, committed]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getJson("/listings/", params)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [params]);

  const pageSize = data.results?.length ? data.results.length : 1;
  const totalPages = Math.max(1, Math.ceil((data.count || 0) / pageSize));

  return (
    <div className="d4-page" style={{ paddingBottom: 80 }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          gap: 16,
          flexWrap: "wrap",
          marginBottom: 18,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: "#111" }}>
            Listings
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 14, color: "#666" }}>
            {data.count?.toLocaleString() ?? "—"} listings indexed across all dealers.
          </p>
        </div>
        <select
          value={ordering}
          onChange={(e) => { setOrdering(e.target.value); setPage(1); }}
          style={{ ...inputStyle, minWidth: 160 }}
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </header>

      <ActiveFilterChips
        filters={committed}
        onRemove={removeFilter}
        onClearAll={clearAllFilters}
      />

      <FilterBar filters={filters} onChange={setFilters} />

      {error && (
        <div style={{
          padding: 12, borderRadius: 10,
          background: "rgba(220,38,38,0.08)", color: "#b91c1c",
          fontSize: 14, marginBottom: 12,
        }}>
          Couldn't load listings: {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 16,
          opacity: loading ? 0.6 : 1,
          transition: "opacity 0.15s",
        }}
      >
        {(data.results || []).map((r) => (
          <Card key={r.id} row={r} />
        ))}
        {!loading && !error && !data.results?.length && (
          <div style={{
            gridColumn: "1 / -1",
            padding: 40, textAlign: "center",
            color: "#666", fontSize: 14,
          }}>
            No listings match those filters.
          </div>
        )}
      </div>

      <Pagination
        page={page}
        totalPages={totalPages}
        onChange={setPage}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Card — one listing in the grid.
// ─────────────────────────────────────────────────────────────────────

function Card({ row }) {
  const mileage = fmtMileage(row);
  const location = [row.city, row.region].filter(Boolean).join(", ");
  const yearMakeModel = [row.year, row.make, row.model].filter(Boolean).join(" ");
  return (
    <article
      style={{
        background: "#fff",
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: 16,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        transition: "transform 0.15s, box-shadow 0.15s",
        cursor: row.listing_url ? "pointer" : "default",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-2px)";
        e.currentTarget.style.boxShadow = "0 12px 28px rgba(0,0,0,0.06)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "none";
      }}
      onClick={() => {
        if (row.listing_url) window.open(row.listing_url, "_blank", "noopener,noreferrer");
      }}
    >
      <div style={{ aspectRatio: "3 / 2", background: "#fafafa" }}>
        <CarThumb
          imageUrl={row.image_url}
          imageSvgUrl={row.image_svg_url}
          alt={yearMakeModel}
          width="100%"
          height="100%"
          rounded={0}
        />
      </div>
      <div style={{ padding: "12px 14px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ fontSize: 12, color: "#888", fontWeight: 500 }}>
          {row.year || "—"}
        </div>
        <div style={{
          fontSize: 15, fontWeight: 700, color: "#111",
          lineHeight: 1.25,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {row.make} {row.model}
        </div>
        {row.trim && (
          <div style={{
            fontSize: 13, color: "#444",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {row.trim}
          </div>
        )}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "baseline",
          marginTop: 4,
        }}>
          <span style={{ fontSize: 17, fontWeight: 800, color: "#111" }}>
            {fmtPrice(row)}
          </span>
          {mileage && (
            <span style={{ fontSize: 12, color: "#666" }}>{mileage}</span>
          )}
        </div>
        <div style={{
          marginTop: 6, paddingTop: 8,
          borderTop: "1px solid rgba(0,0,0,0.06)",
          fontSize: 12, color: "#888",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {row.source_name || row.source_id || "—"}
          {location && <> · {location}</>}
        </div>
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Filter bar — same fields as the old DataTable, laid out inline.
// ─────────────────────────────────────────────────────────────────────

function FilterBar({ filters, onChange }) {
  const set = (key, value) => onChange({ ...filters, [key]: value });
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: 10,
        marginBottom: 18,
        background: "#fff",
        padding: 12,
        borderRadius: 12,
        border: "1px solid rgba(0,0,0,0.06)",
      }}
    >
      <input style={inputStyle} placeholder="Make" value={filters.make || ""}
        onChange={(e) => set("make", e.target.value)} />
      <input style={inputStyle} placeholder="Model" value={filters.model || ""}
        onChange={(e) => set("model", e.target.value)} />
      <input style={inputStyle} placeholder="Year ≥" type="number"
        value={filters.year_min || ""} onChange={(e) => set("year_min", e.target.value)} />
      <input style={inputStyle} placeholder="Year ≤" type="number"
        value={filters.year_max || ""} onChange={(e) => set("year_max", e.target.value)} />
      <input style={inputStyle} placeholder="Price ≥" type="number"
        value={filters.price_min || ""} onChange={(e) => set("price_min", e.target.value)} />
      <input style={inputStyle} placeholder="Price ≤" type="number"
        value={filters.price_max || ""} onChange={(e) => set("price_max", e.target.value)} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Pagination — minimal prev / "page X of Y" / next.
// ─────────────────────────────────────────────────────────────────────

function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null;
  const btn = {
    padding: "8px 14px", borderRadius: 10,
    border: "1px solid rgba(0,0,0,0.12)",
    background: "#fff", color: "#111",
    fontSize: 14, fontWeight: 500,
    cursor: "pointer",
  };
  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, marginTop: 24 }}>
      <button style={btn} disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ← Prev
      </button>
      <span style={{ fontSize: 14, color: "#666" }}>
        Page {page} of {totalPages.toLocaleString()}
      </span>
      <button style={btn} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
        Next →
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Active-filter chips — render the currently-applied URL filters as
// removable pills above the filter bar. Makes drill-down state from
// /cars or /dealers obvious + reversible.
// ─────────────────────────────────────────────────────────────────────

function ActiveFilterChips({ filters, onRemove, onClearAll }) {
  // Display order roughly matches the natural reading: dealer first
  // (where), then year/make/model/trim (what), then price (how much).
  const order = ["source_id", "year", "make", "model", "trim",
                 "year_min", "year_max", "price_min", "price_max"];
  const entries = order
    .filter((k) => k in filters)
    .map((k) => [k, filters[k]]);

  if (entries.length === 0) return null;

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", alignItems: "center",
      gap: 8, marginBottom: 12,
    }}>
      <span style={{ fontSize: 13, color: "#666", fontWeight: 600 }}>
        Filtered by:
      </span>
      {entries.map(([key, value]) => {
        const label = FILTER_CHIP_LABEL[key] || key;
        const display = value === "" ? "(no trim)" : String(value);
        return (
          <span
            key={key}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "4px 6px 4px 10px",
              borderRadius: 99,
              background: "#eef2ff",
              color: "#3730a3",
              fontSize: 12, fontWeight: 600,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <span style={{ opacity: 0.7 }}>{label}:</span>
            <span>{display}</span>
            <button
              type="button"
              onClick={() => onRemove(key)}
              aria-label={`Remove ${label} filter`}
              title={`Remove ${label} filter`}
              style={{
                width: 18, height: 18, borderRadius: 99,
                border: "none", background: "rgba(55,48,163,0.15)",
                color: "#3730a3", cursor: "pointer",
                fontSize: 14, lineHeight: 1, padding: 0,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}
            >
              ×
            </button>
          </span>
        );
      })}
      <button
        type="button"
        onClick={onClearAll}
        style={{
          padding: "4px 10px", borderRadius: 99,
          border: "1px solid rgba(0,0,0,0.10)",
          background: "transparent", color: "#666",
          fontSize: 12, fontWeight: 500, cursor: "pointer",
        }}
      >
        Clear all
      </button>
    </div>
  );
}
