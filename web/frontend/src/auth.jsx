/**
 * Tiny shared-passphrase auth for the chat endpoint.
 *
 * Not user accounts — just a single API key that the user enters once
 * on /login and that gets sent as `X-CarPapi-Auth: <token>` on every
 * API call. The backend validates against the `CARPAPI_API_KEY` env
 * var. When that matches, the request proceeds; otherwise 401.
 *
 * For real users we'd swap this for Cognito or Clerk. The contract
 * (`X-CarPapi-Auth` header) stays the same.
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
import { AUTH_STORAGE_KEY, getApiToken, setApiToken } from "./api.js";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(() => getApiToken());

  // Keep state in sync if another tab logs in/out.
  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === AUTH_STORAGE_KEY) {
        setTokenState(e.newValue || null);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const signIn = useCallback((newToken) => {
    setApiToken(newToken);
    setTokenState(newToken || null);
  }, []);

  const signOut = useCallback(() => {
    setApiToken(null);
    setTokenState(null);
  }, []);

  const value = useMemo(
    () => ({
      token,
      isAuthed: !!token,
      signIn,
      signOut,
    }),
    [token, signIn, signOut],
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
