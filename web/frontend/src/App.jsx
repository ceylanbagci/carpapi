import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Landing from "./pages/Landing.jsx";
import Chat from "./pages/Chat.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Home from "./pages/Home.jsx";
import Cars from "./pages/Cars.jsx";
import Dealers from "./pages/Dealers.jsx";
import Listings from "./pages/Listings.jsx";
import Makes from "./pages/Makes.jsx";
import Models from "./pages/Models.jsx";
import Signup from "./pages/Signup.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Settings from "./pages/Settings.jsx";
import Pricing from "./pages/Pricing.jsx";
import {
  AuthProvider,
  ProtectedRoute,
  StaffProtectedRoute,
} from "./auth.jsx";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route index element={<Landing />} />

        {/* Auth pages — standalone, no sidebar */}
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="signup" element={<Signup />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="reset-password" element={<ResetPassword />} />

        {/* Public pricing page — standalone */}
        <Route path="pricing" element={<Pricing />} />

        {/* Chat — any signed-in user */}
        <Route
          path="chat"
          element={
            <ProtectedRoute>
              <Chat />
            </ProtectedRoute>
          }
        />

        {/* User settings — any signed-in user, no admin sidebar */}
        <Route
          path="settings"
          element={
            <ProtectedRoute>
              <Settings />
            </ProtectedRoute>
          }
        />
        {/* Back-compat: /account → /settings (preserves any old links) */}
        <Route path="account" element={<Navigate to="/settings" replace />} />

        {/* Admin shell — STAFF ONLY. Non-staff users get bounced to
            /settings by StaffProtectedRoute. Sidebar nav lives here. */}
        <Route
          element={
            <StaffProtectedRoute>
              <Layout />
            </StaffProtectedRoute>
          }
        >
          <Route path="dashboard" element={<Home />} />
          <Route path="cars" element={<Cars />} />
          <Route path="dealers" element={<Dealers />} />
          <Route path="listings" element={<Listings />} />
          <Route path="makes" element={<Makes />} />
          <Route path="models" element={<Models />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
