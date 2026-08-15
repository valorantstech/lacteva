import type { MetadataRoute } from "next";

const siteUrl = process.env.LACTEVA_SITE_URL ?? "https://lacteva.example";

// /login is deliberately absent: a hand-over page, noindexed.
const ROUTES = [
  "/",
  "/product",
  "/solutions",
  "/pricing",
  "/why-lacteva",
  "/company",
  "/request-demo",
  "/start-free-trial",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${siteUrl}${route === "/" ? "" : route}`,
    changeFrequency: "monthly",
    priority: route === "/" ? 1 : 0.7,
  }));
}
