import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Monorepo has another lockfile at the repo root; pin the Turbopack workspace
  // root to this app so it doesn't infer the wrong one.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
