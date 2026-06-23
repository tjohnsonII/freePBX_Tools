/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  async rewrites() {
    return [{ source: '/api/:path*', destination: 'http://localhost:8787/api/:path*' }];
  },
};

export default nextConfig;
