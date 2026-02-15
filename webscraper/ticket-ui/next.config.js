/** @type {import('next').NextConfig} */
const proxyTarget = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8787";

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_TICKET_API_PROXY_TARGET: proxyTarget,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${proxyTarget}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
