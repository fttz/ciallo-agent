import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${process.env.API_PROXY_BASE ?? "http://127.0.0.1:8000"}/:path*`
      }
    ];
  }
};

export default nextConfig;
