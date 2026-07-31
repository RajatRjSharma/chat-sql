import type { NextConfig } from "next";

/**
 * Proxy /api (and /health) to the FastAPI backend so the browser talks same-origin.
 * Auth httpOnly cookies then stay first-party — required for reliable login on
 * iOS Safari / Android Chrome (they block cross-site cookies from Vercel→Render).
 *
 * Server-only: API_PROXY_TARGET (e.g. https://your-api.onrender.com)
 * Fallback: NEXT_PUBLIC_API_URL, then local backend.
 */
const proxyTarget = (
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${proxyTarget}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${proxyTarget}/health`,
      },
      {
        source: "/health/:path*",
        destination: `${proxyTarget}/health/:path*`,
      },
    ];
  },
};

export default nextConfig;
