/** @type {import('next').NextConfig} */
const proxyTarget = process.env.TICKET_API_PROXY_TARGET || "http://127.0.0.1:8788";

const nextConfig = {
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_TICKET_API_PROXY_TARGET: proxyTarget,
  },
};

module.exports = nextConfig;
