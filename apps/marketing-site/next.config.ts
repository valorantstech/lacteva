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

  /**
   * MKT-004B: the public editions narrative is retired (packaging is not
   * finalized commercially). Temporary redirect, not permanent, so the URL
   * stays reusable if a pricing/packaging page returns there later.
   */
  async redirects() {
    const redirects = [
      { source: "/editions", destination: "/product", permanent: false },
    ];
    // MKT-004E: /login hands over to the separately deployed authenticated
    // portal when its URL is configured. Unset (local dev without a
    // portal), the /login page itself renders a clear explanation instead
    // of redirecting into nothing.
    const portalUrl = process.env.NEXT_PUBLIC_PORTAL_URL;
    if (portalUrl) {
      redirects.push({
        source: "/login",
        destination: portalUrl,
        permanent: false,
      });
    }
    return redirects;
  },
};

export default nextConfig;
