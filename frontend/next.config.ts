import type { NextConfig } from "next";

// Enforced security headers, incl. an ENFORCED CSP. connect-src is limited to the
// API + our exact S3 bucket (presigned uploads) so an XSS can't exfiltrate PHI to
// an attacker-owned origin; script-src is 'self' (+ inline for Next).
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
// Exact upload bucket origin in prod (e.g. https://<bucket>.s3.us-east-1.amazonaws.com,
// set in Vercel). Falls back to a region-scoped wildcard so uploads still work if
// unset — narrower than the previous global *.s3.amazonaws.com.
const uploadOrigin =
  process.env.NEXT_PUBLIC_UPLOAD_ORIGIN ?? "https://*.s3.us-east-1.amazonaws.com";
const isProd = process.env.NODE_ENV === "production";
// localhost is a dev-only backend; never ship it in the production policy.
const connectSrc = ["'self'", apiOrigin, uploadOrigin, ...(isProd ? [] : ["http://localhost:8000"])]
  .filter(Boolean)
  .join(" ");
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
      `connect-src ${connectSrc}`,
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
