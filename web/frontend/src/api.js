// API client.
//
// VITE_API_BASE behaviour:
//   - default ("/api")          : relative; works in dev (vite proxy) +
//                                 any setup where the API is same-origin
//                                 with the static site.
//   - absolute (https://...)    : production cloud deploys where the API
//                                 lives on a separate host (App Runner).
//                                 The fetch goes cross-origin; the Django
//                                 side needs CORS to allow our origin.
const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const IS_ABSOLUTE = /^https?:\/\//i.test(API_BASE);

function buildUrl(path, params) {
  // Strip leading slash from path so concatenation is consistent.
  const cleanPath = path.startsWith("/") ? path : "/" + path;
  const base = IS_ABSOLUTE
    ? API_BASE.replace(/\/$/, "")
    : API_BASE.replace(/\/$/, "");
  const baseOrigin = IS_ABSOLUTE ? "" : window.location.origin;
  const url = new URL(base + cleanPath, baseOrigin || undefined);
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  return url;
}

export async function getJson(path, params = {}) {
  const url = buildUrl(path, params);
  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return res.json();
}

export async function postJson(path, body) {
  const url = buildUrl(path);
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${url}`);
  }
  return res.json();
}
