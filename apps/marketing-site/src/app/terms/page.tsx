import type { Metadata } from "next";
import Link from "next/link";
import {
  LegalArticle,
  LegalSection,
  P,
  Placeholder,
  Ul,
} from "@/components/legal";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Terms & Conditions",
  description:
    "The terms that govern use of the Lacteva website and the Lacteva dairy operations platform.",
  alternates: { canonical: "/terms" },
};

/**
 * DRAFT for business/legal review (PRE-LAUNCH-002). Structurally complete;
 * the clauses that require counsel — limitation of liability,
 * indemnification, governing law — are explicit <Placeholder>s rather
 * than invented language. Grounded in the actual product: the trial is a
 * request-and-setup process, pricing is communicated separately, and no
 * availability numbers are promised.
 */
export default function TermsPage() {
  return (
    <Section>
      <LegalArticle>
        <div>
          <SectionHeading
            as="h1"
            eyebrow="Legal"
            title="Lacteva Terms & Conditions"
            lede="The terms that govern use of the Lacteva website and the Lacteva platform."
          />
          <p className="text-sm font-medium">Last updated: 15 August 2026</p>
        </div>

        <LegalSection title="1. Introduction">
          <P>
            These terms govern your use of the Lacteva website and, together
            with any applicable customer agreement or order, the Lacteva
            dairy operations platform (the &quot;Service&quot;). Lacteva is
            operated by <Placeholder>[LEGAL ENTITY NAME]</Placeholder>{" "}
            (&quot;Lacteva&quot;, &quot;we&quot;, &quot;us&quot;).
          </P>
        </LegalSection>

        <LegalSection title="2. Acceptance">
          <P>
            By using this website, submitting a demo or trial request, or
            accessing the Service, you agree to these terms. If you are
            acting for an organization, you confirm you have authority to
            accept them on its behalf, and &quot;you&quot; includes that
            organization.
          </P>
        </LegalSection>

        <LegalSection title="3. The Lacteva Service">
          <P>
            Lacteva is a business platform that connects dairy operations —
            milk procurement, collection, customers, delivery, billing,
            payments, settlements, and reporting — in one system, accessed
            through a web application and a mobile application for field
            operations. The features available to you depend on your
            agreement with us.
          </P>
        </LegalSection>

        <LegalSection title="4. Eligibility and authorized users">
          <P>
            The Service is intended for businesses and their authorized
            personnel, not for consumers or children. Access is through
            accounts the customer administers; the customer is responsible
            for deciding who its authorized users are and for what its users
            do in the Service.
          </P>
        </LegalSection>

        <LegalSection title="5. Accounts and access">
          <P>
            You are responsible for keeping credentials confidential and for
            activity under your accounts. Notify us promptly of any suspected
            unauthorized access. Roles and permissions configured in the
            platform determine what each user can see and do; do not attempt
            to exceed them.
          </P>
        </LegalSection>

        <LegalSection title="6. Free trial">
          <P>
            Lacteva offers a 30-day free trial. The current trial process is:
            you submit a trial request through this website, our team reviews
            your requirements and coordinates setup with you, and we prepare a
            trial environment for your organization. Trials are provisioned by
            our team rather than automatically, and we may decline or
            reschedule a trial request. Trial environments are provided for
            evaluation; continuing after the trial is subject to a commercial
            agreement, and neither side is obliged to continue.
          </P>
        </LegalSection>

        <LegalSection title="7. Customer responsibilities">
          <P>You are responsible for:</P>
          <Ul>
            <li>The accuracy of information you submit to the Service</li>
            <li>
              Having the rights and permissions needed to submit information
              about others — such as suppliers, farmers, staff, and buyers —
              and to have it processed in the Service
            </li>
            <li>Complying with the laws that apply to your operations</li>
            <li>Managing your users, roles, and permissions appropriately</li>
          </Ul>
        </LegalSection>

        <LegalSection title="8. Customer data">
          <P>
            Information you submit to the Service remains yours. We process
            it as necessary to provide, secure, maintain, and support the
            Service, as described in our{" "}
            <Link href="/privacy-policy" className="text-primary underline underline-offset-4">
              Privacy Policy
            </Link>{" "}
            and any applicable customer agreement. We do not claim ownership
            of customer-submitted information.
          </P>
        </LegalSection>

        <LegalSection title="9. Acceptable use">
          <P>You must not:</P>
          <Ul>
            <li>Access the Service or another organization&apos;s data without authorization</li>
            <li>Circumvent or probe security or access controls</li>
            <li>Introduce malware or harmful code</li>
            <li>Abuse interfaces or APIs, or disrupt the Service&apos;s operation</li>
            <li>Use the Service for unlawful activity</li>
            <li>Collect data from the Service you are not authorized to collect</li>
            <li>Infringe the rights of others</li>
            <li>Share, sell, or misuse credentials</li>
          </Ul>
        </LegalSection>

        <LegalSection title="10. Intellectual property">
          <P>
            The Lacteva software, website, branding, trademarks, design,
            documentation, and underlying technology are owned by{" "}
            <Placeholder>[LEGAL ENTITY NAME]</Placeholder> or its licensors.
            No rights are granted except as expressly stated in these terms
            or an applicable agreement. Customer-submitted information is
            addressed in section 8.
          </P>
        </LegalSection>

        <LegalSection title="11. Third-party services">
          <P>
            The Service relies on third-party providers — for example
            infrastructure, hosting, and communications providers — and a
            customer may connect or authorize third parties of its own. We
            are not responsible for third-party services we do not control.
          </P>
        </LegalSection>

        <LegalSection title="12. Availability and changes to the Service">
          <P>
            We work to keep the Service reliable and recoverable, but we do
            not promise uninterrupted or error-free operation. Maintenance,
            updates, and factors outside our control can affect availability.
            We may improve or change the Service over time; where a change
            materially reduces the Service a paying customer has subscribed
            to, we will communicate it.
          </P>
        </LegalSection>

        <LegalSection title="13. Fees and subscription">
          <P>
            Commercial pricing and subscription terms are communicated
            separately — through an order form, subscription agreement,
            proposal, or other commercial arrangement between you and us. Use
            of the trial is free for its 30-day period.
          </P>
        </LegalSection>

        <LegalSection title="14. Suspension and termination">
          <P>
            We may suspend or terminate access for material breach of these
            terms, for security reasons, where required by law, or where a
            trial or agreement ends. Where reasonable, we will notify you and
            give you an opportunity to address the issue. Provisions that by
            their nature should survive termination survive it.
          </P>
        </LegalSection>

        <LegalSection title="15. Disclaimers">
          <P>
            Except as expressly stated in these terms or an applicable
            customer agreement, the Service is provided &quot;as is&quot; and
            &quot;as available&quot;, without warranties of any kind, whether
            express or implied, to the extent permitted by applicable law.
          </P>
          <P>
            <Placeholder>
              [LEGAL REVIEW REQUIRED — DISCLAIMER LANGUAGE TO BE CONFIRMED BY
              COUNSEL]
            </Placeholder>
          </P>
        </LegalSection>

        <LegalSection title="16. Limitation of liability">
          <P>
            <Placeholder>
              [LEGAL REVIEW REQUIRED — LIMITATION OF LIABILITY LANGUAGE]
            </Placeholder>
          </P>
        </LegalSection>

        <LegalSection title="17. Indemnification">
          <P>
            <Placeholder>
              [LEGAL REVIEW REQUIRED — INDEMNIFICATION LANGUAGE]
            </Placeholder>
          </P>
        </LegalSection>

        <LegalSection title="18. Confidentiality">
          <P>
            Each side may receive non-public information from the other in
            connection with the Service. The receiving side will use it only
            for purposes of the relationship and protect it with reasonable
            care, except where disclosure is required by law or the
            information is or becomes public through no fault of the
            receiver. A customer agreement may contain more specific
            confidentiality terms, which take precedence.
          </P>
        </LegalSection>

        <LegalSection title="19. Governing law and jurisdiction">
          <P>
            <Placeholder>
              [GOVERNING LAW AND JURISDICTION — BUSINESS/LEGAL DECISION
              REQUIRED]
            </Placeholder>
          </P>
        </LegalSection>

        <LegalSection title="20. Changes to these terms">
          <P>
            We may update these terms from time to time. The &quot;Last
            updated&quot; date above shows when they last changed; material
            changes will be reflected on this page, and continued use of the
            Service after a change means acceptance of the updated terms.
          </P>
        </LegalSection>

        <LegalSection title="21. Contact">
          <P>
            Questions about these terms can be sent to{" "}
            <Placeholder>[GENERAL CONTACT EMAIL]</Placeholder> or by post to{" "}
            <Placeholder>[REGISTERED/BUSINESS ADDRESS]</Placeholder>.
          </P>
        </LegalSection>
      </LegalArticle>
    </Section>
  );
}
