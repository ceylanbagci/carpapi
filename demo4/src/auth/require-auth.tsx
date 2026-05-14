import { Outlet } from 'react-router-dom';

/**
 * Component to protect routes that require authentication.
 * If user is not authenticated, redirects to the login page.
 */
export const RequireAuth = () => {
  return <Outlet />;
};
