/** @type {import('next').NextConfig} */

// Hardened baseline response headers (mirrors backend security headers).
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig = {
  // Enforce strict mode to surface double-invoked effects in development.
  reactStrictMode: true,
  // Required by the production multi-stage Docker build (docker/frontend/Dockerfile.prod).
  output: "standalone",
  async redirects() {
    return [
      {
        source: "/operational-monitoring",
        destination: "/monitoring",
        permanent: true,
      },
      {
        source: "/operational-monitoring/:path*",
        destination: "/monitoring",
        permanent: true,
      },
      {
        source: "/worker-monitoring",
        destination: "/monitoring",
        permanent: true,
      },
      {
        source: "/worker-monitoring/:path*",
        destination: "/monitoring",
        permanent: true,
      },
    ];
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
