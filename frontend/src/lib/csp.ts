/**
 * Content-Security-Policy, built per request in src/proxy.ts with a fresh nonce.
 *
 * script-src uses the nonce + 'strict-dynamic' instead of 'unsafe-inline', so an
 * injected <script> never executes; Next applies the nonce to its own bootstrap
 * scripts when the CSP arrives as a REQUEST header, and the one hand-written
 * inline script (theme bootstrap in app/layout.tsx) reads it from `x-nonce`.
 * connect-src is limited to the API + our exact S3 bucket so an XSS that somehow
 * ran still couldn't exfiltrate PHI to an attacker origin.
 */

const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// Presigned S3 uploads: us-east-1 signs to the GLOBAL endpoint
// (<bucket>.s3.amazonaws.com); other configs use the REGIONAL one
// (<bucket>.s3.us-east-1.amazonaws.com). Allow both forms of the one bucket so the
// upload PUT is never CSP-blocked. Set NEXT_PUBLIC_UPLOAD_ORIGIN (in either form)
// to pin the bucket; falls back to region-scoped wildcards if unset.
export function uploadOrigins(
  isProd = process.env.NODE_ENV === "production",
): string[] {
  // Dot-tolerant: S3 bucket names may contain dots, so capture up to ".s3" /
  // ".s3-" rather than a single label.
  const bucket = process.env.NEXT_PUBLIC_UPLOAD_ORIGIN?.match(
    /^https:\/\/(.+?)\.s3[.-]/,
  )?.[1];
  if (!bucket) {
    // Fail CLOSED in production: a wildcard would make any attacker S3 bucket an
    // allowed exfil destination, defeating the whole point of pinning
    // connect-src. A missing/unparseable upload origin in prod is a config bug
    // that must fail the build/boot loudly, not silently widen the policy.
    if (isProd) {
      throw new Error(
        "NEXT_PUBLIC_UPLOAD_ORIGIN is unset or unparseable in production — refusing to widen CSP connect-src to all of S3.",
      );
    }
    return [
      "https://*.s3.amazonaws.com",
      "https://*.s3.us-east-1.amazonaws.com",
    ];
  }
  return [
    `https://${bucket}.s3.amazonaws.com`,
    `https://${bucket}.s3.us-east-1.amazonaws.com`,
  ];
}

export function buildCsp(
  nonce: string,
  isProd = process.env.NODE_ENV === "production",
): string {
  // localhost is a dev-only backend; never ship it in the production policy.
  const connectSrc = [
    "'self'",
    apiOrigin,
    ...uploadOrigins(isProd),
    ...(isProd ? [] : ["http://localhost:8000", "ws://localhost:3000"]),
  ]
    .filter(Boolean)
    .join(" ");
  // Dev needs eval for React Refresh; production never does.
  const scriptSrc = `'self' 'nonce-${nonce}' 'strict-dynamic'${isProd ? "" : " 'unsafe-eval'"}`;
  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    ...(isProd ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}
