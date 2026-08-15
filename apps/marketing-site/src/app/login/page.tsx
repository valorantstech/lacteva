import type { Metadata } from "next";
import { LinkButton } from "@/components/link-button";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Login",
  description: "Sign in to the Lacteva platform.",
  // A hand-over page, not content — keep it out of search results.
  robots: { index: false, follow: false },
};

/**
 * When NEXT_PUBLIC_PORTAL_URL is configured, next.config.ts redirects
 * /login to the authenticated portal and this page is never reached. It
 * exists for the unconfigured case (local development), where a clear
 * explanation beats a dead redirect — and it never hardcodes a portal URL.
 */
export default function LoginPage() {
  const portalUrl = process.env.NEXT_PUBLIC_PORTAL_URL;
  return (
    <Section>
      <SectionHeading
        as="h1"
        eyebrow="Login"
        title="Sign in to Lacteva"
        lede={
          portalUrl
            ? "Continue to the Lacteva platform to sign in."
            : "The Lacteva platform is a separate application. Its address is not configured in this environment (NEXT_PUBLIC_PORTAL_URL) — if you arrived here on the public site, please use the trial or demo links below."
        }
      />
      <div className="flex flex-wrap items-center gap-3">
        {portalUrl ? (
          <a
            href={portalUrl}
            className="inline-flex h-11 items-center rounded-lg bg-primary px-6 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85"
          >
            Continue to login
          </a>
        ) : null}
        <LinkButton href="/start-free-trial" variant={portalUrl ? "outline" : "default"}>
          Start Free Trial
        </LinkButton>
        <LinkButton href="/request-demo" variant="outline">
          Book a Demo
        </LinkButton>
      </div>
    </Section>
  );
}
