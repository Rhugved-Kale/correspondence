import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

// We serve the frontend on :5173 and proxy /api/* to FastAPI on :8000.
// During dev, the user runs `npm run dev` for the UI and a separate
// `uvicorn backend.main:app` for the API. In production we'd serve the
// built `dist/` from FastAPI directly, but local dev is simpler with two
// processes.
const PUBLIC_URL =
  process.env.VITE_PUBLIC_URL ||
  (process.env.VERCEL_PROJECT_PRODUCTION_URL
    ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
    : "https://correspondence-demo.vercel.app");

export default defineConfig({
  // Absolute URLs for OG tags and the share-card footer. Scrapers do not
  // resolve relative paths, and a hardcoded guess at the domain is how
  // you ship link previews that 404.
  define: { __PUBLIC_URL__: JSON.stringify(PUBLIC_URL) },
  plugins: [
    react(),
    {
      name: "public-url-in-html",
      transformIndexHtml(html) {
        return html.replaceAll("__PUBLIC_URL__", PUBLIC_URL);
      },
    },
    // Custom middleware: serve /output/*.json and /demo/*.json straight
    // from the project root. The pipeline writes to output/ and the demo
    // fixture lives in demo/, and we want the frontend reading the live
    // files rather than copies in public/ that go stale on every run.
    {
      name: "serve-output-json",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && (req.url.startsWith("/output/") || req.url.startsWith("/demo/"))) {
            const relPath = req.url.replace(/^\/+/, "");
            const filePath = path.resolve(__dirname, "..", relPath);
            if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
              res.setHeader("Content-Type", "application/json; charset=utf-8");
              res.setHeader("Cache-Control", "no-store");
              fs.createReadStream(filePath).pipe(res);
              return;
            }
          }
          next();
        });
      },
    },
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    fs: {
      allow: [".."],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
