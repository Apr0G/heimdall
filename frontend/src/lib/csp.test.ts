import { afterEach, describe, expect, it, vi } from "vitest";

import { uploadOrigins } from "./csp";

const ENV = process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;

afterEach(() => {
  process.env.NEXT_PUBLIC_UPLOAD_ORIGIN = ENV;
  vi.unstubAllEnvs();
});

describe("uploadOrigins", () => {
  it("pins both endpoint forms of the configured bucket", () => {
    process.env.NEXT_PUBLIC_UPLOAD_ORIGIN =
      "https://heimdall-documents-abc123.s3.amazonaws.com";
    expect(uploadOrigins(true)).toEqual([
      "https://heimdall-documents-abc123.s3.amazonaws.com",
      "https://heimdall-documents-abc123.s3.us-east-1.amazonaws.com",
    ]);
  });

  it("FAILS CLOSED in production when the upload origin is unset", () => {
    delete process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;
    // A wildcard fallback in prod would let any attacker S3 bucket be an allowed
    // exfil destination — must throw, not widen.
    expect(() => uploadOrigins(true)).toThrow(/refusing to widen CSP/i);
  });

  it("falls back to wildcards only in non-production", () => {
    delete process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;
    expect(uploadOrigins(false)).toEqual([
      "https://*.s3.amazonaws.com",
      "https://*.s3.us-east-1.amazonaws.com",
    ]);
  });
});
