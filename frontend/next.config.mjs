/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Standalone output produces a self-contained server in .next/standalone that
  // needs no node_modules in the runtime image — the slim production deploy
  // path recommended by Next.js. See infra/Dockerfile.frontend.
  output: "standalone",
  async rewrites() {
    return [
      // Proxy /api and /health to the FastAPI backend so the browser uses
      // same-origin requests (no CORS headaches in dev).
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
