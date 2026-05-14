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
