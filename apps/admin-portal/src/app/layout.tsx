import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Lacteva Admin Portal",
  description: "Administration portal for the Lacteva platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <nav className="border-b border-border bg-background/95 px-8 py-2 text-sm">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-1">
            <Link className="font-semibold" href="/">
              Lacteva
            </Link>
            <a className="text-muted-foreground hover:text-foreground" href="/centers">
              Centers
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/suppliers">
              Suppliers
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/transactions">
              Transactions
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/rate-cards">
              Rate cards
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/matrices">
              Matrices
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/resolve">
              Playground
            </a>
            <a className="text-muted-foreground hover:text-foreground" href="/settlements">
              Settlements
            </a>
            <a className="ml-auto text-muted-foreground hover:text-foreground" href="/login">
              Sign in
            </a>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
