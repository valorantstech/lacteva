import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * PORTAL-001 / F-03: build a self-contained server bundle.
   *
   * The portal is no longer a static site — it runs route handlers that hold
   * the session cookie and proxy to the platform (F-11), so it needs a Node
   * process. `standalone` emits one with only the dependencies it actually
   * imports, which is what lets the production image skip `node_modules`
   * entirely and stay small.
   */
  output: "standalone",

  /**
   * The portal sits behind the same nginx as the API and is the only thing
   * that talks to the platform, so it does not need to advertise a version.
   */
  poweredByHeader: false,
};

export default nextConfig;
