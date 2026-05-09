import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar.jsx";
import Header from "./Header.jsx";
import Footer from "./Footer.jsx";

export default function Layout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="d4-app">
      <Sidebar open={open} />
      <div className="d4-main">
        <Header onToggleSidebar={() => setOpen((v) => !v)} />
        <main className="d4-content">
          <Outlet />
        </main>
        <Footer />
      </div>
    </div>
  );
}
