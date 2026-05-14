import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Landing from "./pages/Landing.jsx";
import Chat from "./pages/Chat.jsx";
import Home from "./pages/Home.jsx";
import Cars from "./pages/Cars.jsx";
import Dealers from "./pages/Dealers.jsx";
import Listings from "./pages/Listings.jsx";
import Makes from "./pages/Makes.jsx";
import Models from "./pages/Models.jsx";
import Login from "./pages/Login.jsx";
import Signup from "./pages/Signup.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Account from "./pages/Account.jsx";
import Pricing from "./pages/Pricing.jsx";

export default function App() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route path="chat" element={<Chat />} />
      {/* Auth pages — standalone, no sidebar */}
      <Route path="login" element={<Login />} />
      <Route path="signup" element={<Signup />} />
      <Route path="forgot-password" element={<ForgotPassword />} />
      <Route path="reset-password" element={<ResetPassword />} />
      {/* Public pricing page — standalone */}
      <Route path="pricing" element={<Pricing />} />
      {/* Admin / authenticated pages — wrapped in Layout (with sidebar) */}
      <Route element={<Layout />}>
        <Route path="dashboard" element={<Home />} />
        <Route path="cars" element={<Cars />} />
        <Route path="dealers" element={<Dealers />} />
        <Route path="listings" element={<Listings />} />
        <Route path="makes" element={<Makes />} />
        <Route path="models" element={<Models />} />
        <Route path="account" element={<Account />} />
      </Route>
    </Routes>
  );
}
