/**
 * Auth context for the SPA.
 *
 * Wraps localStorage-backed JWT auth (access + refresh + user) from
 * api.js into a React context so any component can:
 *   - read `useAuth().user` to render a name/avatar/logged-out state
 *   - call `useAuth().signIn(auth)` after login/register
 *   - call `useAuth().signOut()` to clear local state
 *
 * Cross-tab logout: a `storage` listener mirrors changes from other
 * tabs so signing out in one tab signs out the rest.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Navigate, useLocation } from "react-router-dom";
import {
  AUTH_STORAGE_KEY,
  getAuth,
  login as apiLogin,
  logout as apiLogout,
  setAuth,
} from "./api.js";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuthState] = useState(() => getAuth());

  // Mirror cross-tab changes.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === AUTH_STORAGE_KEY) {
        try {
          setAuthState(e.newValue ? JSON.parse(e.newValue) : null);
        } catch {
          setAuthState(null);
        }
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // Dev-only auto-login. Skip the login form entirely when we're in
  // Vite dev mode AND the opt-in env var is set. Reads credentials from
  // VITE_DEV_LOGIN_EMAIL / VITE_DEV_LOGIN_PASSWORD in
  // web/frontend/.env.local (gitignored). Production builds NEVER
  // enter this branch — import.meta.env.DEV is hard-coded to false at
  // Vite-build time.
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    if (import.meta.env.VITE_DEV_AUTOLOGIN !== "true") return;
    if (auth && auth.access) return;  // already authed; nothing to do

    const email = import.meta.env.VITE_DEV_LOGIN_EMAIL;
    const password = import.meta.env.VITE_DEV_LOGIN_PASSWORD;
    if (!email || !password) {
      console.warn(
        "[auth] VITE_DEV_AUTOLOGIN=true but VITE_DEV_LOGIN_EMAIL / " +
        "VITE_DEV_LOGIN_PASSWORD are not set in .env.local — skipping.",
      );
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const fresh = await apiLogin({ email, password });
        if (!cancelled) setAuthState(fresh);
        console.info("[auth] dev auto-login as", fresh.user?.email);
      } catch (err) {
        console.warn("[auth] dev auto-login failed:", err.message || err);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const signIn = useCallback((newAuth) => {
    setAuth(newAuth);
    setAuthState(newAuth || null);
  }, []);

  const signOut = useCallback(async () => {
    await apiLogout(); // best-effort POST + clears localStorage
    setAuthState(null);
  }, []);

  const value = useMemo(
    () => ({
      auth,
      user: auth ? auth.user : null,
      isAuthed: !!(auth && auth.access),
      signIn,
      signOut,
    }),
    [auth, signIn, signOut],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

/**
 * Wraps a route. If the user isn't authed, bounces to /login with a
 * ?next= param so we can return them to where they were headed.
 */
export function ProtectedRoute({ children }) {
  const { isAuthed } = useAuth();
  const location = useLocation();
  if (!isAuthed) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return children;
}

/**
 * Wraps the admin shell. Non-authed users → /login.
 * Authed-but-non-staff users → /settings (they don't see admin chrome).
 *
 * `is_staff` comes from the backend user object (`CarPapiUserSerializer`)
 * and reflects Django's auth flag set via /admin/. Only true admins
 * see the /dashboard, /cars, /listings, /makes, /models, /dealers
 * tables. Regular users live at /chat + /settings.
 */
export function StaffProtectedRoute({ children }) {
  const { isAuthed, user } = useAuth();
  const location = useLocation();
  if (!isAuthed) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  if (!user?.is_staff) {
    // Logged in but not staff — send them somewhere useful.
    return <Navigate to="/settings" replace />;
  }
  return children;
}
