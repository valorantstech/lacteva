import type { MetadataRoute } from "next";

const siteUrl = process.env.LACTEVA_SITE_URL ?? "https://lacteva.example";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/api/", "/login"],
    },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
