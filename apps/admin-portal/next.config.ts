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

  /**
   * DEMO-009: keep the build inside the memory the build box actually has.
   *
   * Next.js fans static generation out to one worker per CPU, and each worker
   * is a full Node heap. On the small instance that both builds and serves
   * this platform that produced `spawn ENOMEM` once the app passed ~30 routes.
   * Two workers is slower and finishes; fifteen is faster and does not.
   *
   * `webpackMemoryOptimizations` is the reduction the framework's own memory
   * guide recommends — slightly longer compiles for a lower peak.
   *
   * Both are cheaper than resizing the instance for a build that does not need
   * the room.
   */
  experimental: {
    cpus: 2,
    webpackMemoryOptimizations: true,
  },
};

export default nextConfig;
