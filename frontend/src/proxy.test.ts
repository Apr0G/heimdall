/**
 * The route matcher decides which requests the proxy never sees — and so
 * which ones get neither the login redirect nor a CSP header. Next compiles a
 * single "/(regex)" matcher with path-to-regexp, which for this shape is the
 * same as anchoring the pattern as a plain RegExp.
 */
import { describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({ NextResponse: {} }));

import { config } from "./proxy";

const matcher = new RegExp(`^${config.matcher[0]}$`);

describe("proxy matcher", () => {
  it("skips Next internals and root-level static files only", () => {
    for (const path of [
      "/_next/static/chunks/main.js",
      "/_next/image",
      "/favicon.ico",
      "/file.svg",
      "/logo.png",
    ]) {
      expect(matcher.test(path), path).toBe(false);
    }
  });

  it("gates app routes even when the path ends like an image", () => {
    for (const path of [
      "/",
      "/login",
      "/pre-checks",
      "/pre-checks/anything.png",
      "/cases/x/y.svg",
      "/api/.ico",
    ]) {
      expect(matcher.test(path), path).toBe(true);
    }
  });
});
