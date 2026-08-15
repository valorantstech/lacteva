import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Same deployment shape as apps/admin-portal: a self-contained Node server
   * bundle. The site is mostly static pages, but the demo-request route
   * handler needs a process, and one deployment architecture beats two.
   */
  output: "standalone",

  /**
   * Public-facing; no reason to advertise the framework version.
   */
  poweredByHeader: false,

  /**
   * Same memory discipline as the admin portal (DEMO-009): the emergency
   * fallback is building on the small host that serves the platform, where
   * strict overcommit refuses forks. One worker finishes; fifteen do not.
   */
  experimental: {
    cpus: 1,
    webpackMemoryOptimizations: true,
  },
};

export default nextConfig;
