import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const here = path.dirname(fileURLToPath(import.meta.url));
const LANDING_PATH = path.resolve(here, "public", "landing.html");

/**
 * In production, CloudFront's DefaultRootObject is `landing.html`,
 * so `https://<cf>/` serves the marketing page directly without
 * `/landing.html` in the URL bar. In dev, Vite by default serves the
 * SPA shell (index.html) at `/` and the React Router index route
 * renders nothing — leaving you with a blank page at localhost:5173.
 *
 * This tiny middleware mirrors CloudFront's behavior locally: bare
 * GET `/` reads + returns `public/landing.html`. Every other path
 * (including direct GET `/landing.html`) falls through to Vite's
 * normal handling, so the SPA, the HMR, and the proxy all still
 * work for `/chat`, `/login`, `/api/...`, etc.
 */
function landingAsRoot() {
  return {
    name: "carpapi:serve-landing-as-root",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if ((req.method === "GET" || req.method === "HEAD") && req.url === "/") {
          try {
            const html = fs.readFileSync(LANDING_PATH);
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.setHeader("Cache-Control", "no-cache");
            res.end(html);
            return;
          } catch (err) {
            // fall through to Vite's default (renders the SPA shell)
            // if landing.html isn't there yet.
            console.warn(
              "[carpapi:serve-landing-as-root]",
              "landing.html not found at",
              LANDING_PATH,
              err.message,
            );
          }
        }
        next();
      });
    },
    configurePreviewServer(server) {
      // Same behavior under `npm run preview` (production build).
      server.middlewares.use((req, res, next) => {
        if ((req.method === "GET" || req.method === "HEAD") && req.url === "/") {
          try {
            const built = path.resolve(here, "dist", "landing.html");
            const file = fs.existsSync(built) ? built : LANDING_PATH;
            res.setHeader("Content-Type", "text/html; charset=utf-8");
            res.setHeader("Cache-Control", "no-cache");
            res.end(fs.readFileSync(file));
            return;
          } catch {
            /* fall through */
          }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), landingAsRoot()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/media": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 4173,
  },
});
