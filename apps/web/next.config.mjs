/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL || "http://localhost:8000";
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  compress: false, // keep Server-Sent Events unbuffered through the proxy
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};
export default nextConfig;
