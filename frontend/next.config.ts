import type { NextConfig } from "next";

// Enforced security headers, incl. an ENFORCED CSP. connect-src is limited to the
// API + S3 (presigned uploads) so an XSS can't exfiltrate to arbitrary origins;
// script-src is 'self' (+ inline for Next) so external scripts can't load.
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      `connect-src 'self' ${apiOrigin} https://*.s3.amazonaws.com https://*.s3.us-east-1.amazonaws.com http://localhost:8000`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  // Monorepo has another lockfile at the repo root; pin the Turbopack workspace
  // root to this app so it doesn't infer the wrong one.
  turbopack: {
    root: __dirname,
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
