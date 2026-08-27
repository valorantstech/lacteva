import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ScrollMotion } from "@/components/scroll-motion";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Placeholder origin until the public domain is decided (a commercial
// decision, per Master/Vision) — set LACTEVA_SITE_URL at build time.
const siteUrl = process.env.LACTEVA_SITE_URL ?? "https://lacteva.example";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Lacteva — Connected Dairy Operations Platform",
    template: "%s — Lacteva",
  },
  description:
    "Run your dairy operations as one connected business. Lacteva connects milk procurement, collection, customers, delivery, billing, payments, and reporting in one dairy operations platform.",
  openGraph: {
    siteName: "Lacteva",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
  },
};

/**
 * Conservative structured data: identity only. No ratings, reviews,
 * prices, or counts — none exist to claim.
 */
const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "Phoenix Software",
      url: siteUrl,
      brand: { "@type": "Brand", name: "Lacteva" },
    },
    {
      "@type": "SoftwareApplication",
      name: "Lacteva",
      url: siteUrl,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      description:
        "Connected dairy operations platform: milk procurement, collection, customers, delivery, billing, payments, and reporting in one system.",
    },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
        >
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
        <ScrollMotion />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
      </body>
    </html>
  );
}
