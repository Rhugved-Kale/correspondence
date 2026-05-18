import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

// We serve the frontend on :5173 and proxy /api/* to FastAPI on :8000.
// During dev, the user runs `npm run dev` for the UI and a separate
// `uvicorn backend.main:app` for the API. In production we'd serve the
// built `dist/` from FastAPI directly, but local dev is simpler with two
// processes.
export default defineConfig({
  plugins: [
    react(),
    // Custom middleware: serve /output/people.json straight from the
    // project root's output/ folder. The pipeline writes there, and we
    // want the frontend to read the live file without copying it into
    // public/ (which would go stale every time generate runs).
    {
      name: "serve-output-json",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && req.url.startsWith("/output/")) {
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
