import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Landing from "./pages/Landing.jsx";
import Home from "./pages/Home.jsx";
import Cars from "./pages/Cars.jsx";
import Dealers from "./pages/Dealers.jsx";
import Listings from "./pages/Listings.jsx";
import Makes from "./pages/Makes.jsx";
import Models from "./pages/Models.jsx";

export default function App() {
  return (
    <Routes>
      <Route index element={<Landing />} />
      <Route element={<Layout />}>
        <Route path="dashboard" element={<Home />} />
        <Route path="cars" element={<Cars />} />
        <Route path="dealers" element={<Dealers />} />
        <Route path="listings" element={<Listings />} />
        <Route path="makes" element={<Makes />} />
        <Route path="models" element={<Models />} />
      </Route>
    </Routes>
  );
}
