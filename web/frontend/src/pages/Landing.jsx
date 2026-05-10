import { useEffect } from "react";

/**
 * The landing page is now a self-contained static page (GSAP +
 * ScrollTrigger, no framework) served by Vite from public/landing.html.
 * This component just hands off — first hit on '/' bounces straight
 * there with no React render flash.
 */
export default function Landing() {
  useEffect(() => {
    window.location.replace("/landing.html");
  }, []);
  return null;
}
