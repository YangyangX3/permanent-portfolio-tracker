import type { NextConfig } from "next";

const backendOrigin = process.env.PP_BACKEND_ORIGIN || "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  rewrites: async () => {
    return [
      { source: "/health", destination: `${backendOrigin}/health` },
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` }
    ];
  }
};

export default nextConfig;

