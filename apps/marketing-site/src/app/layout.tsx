import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
    default: "Lacteva — the dairy platform farmers can check",
    template: "%s — Lacteva",
  },
  description:
    "Collect milk offline, price it explainably, settle it in one click, pay it, prove it. Lacteva digitizes the dairy value chain for organizations that today run on paper.",
  openGraph: {
    siteName: "Lacteva",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
