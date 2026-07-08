/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // Standalone output produces a self-contained server in .next/standalone that
  // needs no node_modules in the runtime image — the slim production deploy
  // path recommended by Next.js. See infra/Dockerfile.frontend.
  output: "standalone",
  // generate-note (local mlx-whisper + ollama SOAP drafting) can take well
  // over a minute on a multi-minute recording — Next's rewrite proxy default
  // timeout is too short for that and resets the connection mid-request.
  experimental: {
    proxyTimeout: 180_000,
  },
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
