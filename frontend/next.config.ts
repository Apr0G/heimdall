import type { NextConfig } from "next";

// Enforced security headers. The Content-Security-Policy itself is emitted per
// request by src/proxy.ts (it carries a nonce, so script-src needs no
// 'unsafe-inline'); the connect-src allowlist is built in src/lib/csp.ts and
// shared. Everything static lives here.

const securityHeaders = [
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

const nextConfig: NextConfig = {
  // No `x-powered-by: Next.js` — a free framework fingerprint for anyone
  // probing the site (prod check PLOW-04).
  poweredByHeader: false,
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
