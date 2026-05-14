/**
 * The marketing landing page is a self-contained static page
 * (GSAP + ScrollTrigger, no framework) at `public/landing.html`.
 *
 * It's served as CloudFront's *default root object* — visiting `/`
 * fetches `landing.html` directly, so the URL bar stays clean (no
 * client-side bounce to `/landing.html` and no visible string).
 *
 * This React component is only reached via the SPA fallback for
 * unknown deep-link paths; we render nothing so the user doesn't
 * see a flash before the route resolves.
 */
export default function Landing() {
  return null;
}
