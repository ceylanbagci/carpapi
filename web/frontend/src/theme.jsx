/**
 * App-wide light/dark theme.
 *
 *   - `useTheme()` returns `{ theme, setTheme, toggleTheme }`. Reads
 *     and writes `localStorage["carpapi-theme"]`, and mirrors the
 *     value to `<html data-theme="…">` so every page that ships a
 *     `[data-theme="dark"]` CSS variant responds in one swap.
 *   - First-visit default is the OS `prefers-color-scheme`.
 *   - No React Context: every hook subscribes to a tiny in-module
 *     event-target so cross-tree updates stay in sync without
 *     forcing a Provider wrapper around every public route.
 */
import { useEffect, useState } from "react";

const STORAGE_KEY = "carpapi-theme";
const bus = typeof window === "undefined" ? null : new EventTarget();

function readInitial() {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark" : "light";
}

function applyToDocument(theme) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

// Apply once at module load so the first paint already has the right
// data-attribute before any component mounts. Safe to no-op on SSR.
if (typeof document !== "undefined") {
  applyToDocument(readInitial());
}

export function useTheme() {
  const [theme, setThemeState] = useState(readInitial);

  // Listen for cross-component updates broadcast by `setTheme` below.
  useEffect(() => {
    if (!bus) return;
    const handler = (e) => setThemeState(e.detail);
    bus.addEventListener("change", handler);
    return () => bus.removeEventListener("change", handler);
  }, []);

  // Listen for the OS preference flipping while the app is open, but
  // only when the user hasn't expressed a saved choice.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const handler = (e) => {
      if (window.localStorage.getItem(STORAGE_KEY)) return;
      const next = e.matches ? "dark" : "light";
      applyToDocument(next);
      setThemeState(next);
      bus.dispatchEvent(new CustomEvent("change", { detail: next }));
    };
    mq.addEventListener?.("change", handler);
    return () => mq.removeEventListener?.("change", handler);
  }, []);

  const setTheme = (next) => {
    if (next !== "light" && next !== "dark") return;
    try { window.localStorage.setItem(STORAGE_KEY, next); } catch { /* ignored */ }
    applyToDocument(next);
    setThemeState(next);
    bus.dispatchEvent(new CustomEvent("change", { detail: next }));
  };

  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");

  return { theme, setTheme, toggleTheme };
}
