import type { MetadataRoute } from "next";

const siteUrl = process.env.LACTEVA_SITE_URL ?? "https://lacteva.example";

const ROUTES = [
  "/",
  "/product",
  "/editions",
  "/why-lacteva",
  "/company",
  "/request-demo",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${siteUrl}${route === "/" ? "" : route}`,
    changeFrequency: "monthly",
    priority: route === "/" ? 1 : 0.7,
  }));
}
