import type { Metadata } from "next";
import {
  LegalArticle,
  LegalSection,
  P,
  Placeholder,
  Ul,
} from "@/components/legal";
import { Section, SectionHeading } from "@/components/section";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description:
    "How Lacteva handles information collected through this website and processed through the Lacteva platform.",
  alternates: { canonical: "/privacy-policy" },
};

/**
 * DRAFT for business/legal review (PRE-LAUNCH-002). Every statement about
 * the website and platform below is grounded in the actual implementation;
 * every fact that is not yet decided renders as an explicit <Placeholder>.
 * Do not remove placeholders by inventing values — they are resolved by
 * the product owner and legal counsel, then replaced here.
 */
export default function PrivacyPolicyPage() {
  return (
    <Section>
      <LegalArticle>
        <div>
          <SectionHeading
            as="h1"
            eyebrow="Legal"
            title="Lacteva Privacy Policy"
            lede="How we handle information collected through this website and processed through the Lacteva platform."
          />
          <p className="text-sm font-medium">Last updated: 15 August 2026</p>
        </div>

        <LegalSection title="1. Introduction">
          <P>
            Lacteva is a dairy operations platform operated by{" "}
            <Placeholder>[LEGAL ENTITY NAME]</Placeholder> (&quot;Lacteva&quot;,
            &quot;we&quot;, &quot;us&quot;). This policy explains how we handle
            personal information in two distinct contexts:
          </P>
          <Ul>
            <li>
              <strong>This marketing website</strong> — the public pages you
              are reading now, including the demo-request and free-trial
              request forms and our communications with prospective customers.
            </li>
            <li>
              <strong>The Lacteva platform</strong> — the software service our
              customers use to run their dairy operations, where information
              is submitted by and on behalf of those customers.
            </li>
          </Ul>
          <P>
            Where the platform is concerned, our customer (the dairy business)
            decides what information to submit; we process it to provide the
            service, as described below and in the applicable customer
            agreement.
          </P>
        </LegalSection>

        <LegalSection title="2. Information collected through this website">
          <P>
            The only personal information this website collects is what you
            submit through the demo-request and trial-request forms:
          </P>
          <Ul>
            <li>Name</li>
            <li>Work email address</li>
            <li>Organization name</li>
            <li>Country</li>
            <li>Phone number (optional)</li>
            <li>Type of organization (optional)</li>
            <li>Approximate daily milk volume (optional)</li>
            <li>Anything you choose to tell us in the message field</li>
            <li>Whether your request is for a demo or a free trial</li>
          </Ul>
          <P>
            The website does not collect information you do not type into a
            form. It does not use analytics, advertising, or tracking
            technologies (see &quot;Cookies&quot; below).
          </P>
        </LegalSection>

        <LegalSection title="3. Information processed through the Lacteva platform">
          <P>
            Depending on how the service is used, Lacteva may process
            information submitted by a customer about individuals involved in
            that customer&apos;s operations. Based on the platform&apos;s
            current capabilities, this can include:
          </P>
          <Ul>
            <li>User accounts, roles, and permissions of the customer&apos;s staff</li>
            <li>
              Supplier and farmer records, including identification details and
              bank account details the customer records for settlement and
              payment
            </li>
            <li>Milk collection records, including quantity and quality readings</li>
            <li>Pricing, rate card, and settlement records</li>
            <li>Customer (buyer) records, delivery plans, and delivery records</li>
            <li>Billing, invoice, payment, and receipt records</li>
            <li>Notification and delivery-record logs</li>
            <li>Audit and activity records of actions taken in the platform</li>
          </Ul>
          <P>
            This information belongs to the operational relationship between
            our customer and the people they work with. The customer is
            responsible for having the right to submit it; we process it to
            provide, secure, maintain, and support the service.
          </P>
        </LegalSection>

        <LegalSection title="4. How information is used">
          <P>We use information for the purposes it was provided for:</P>
          <Ul>
            <li>Responding to enquiries and demo requests</li>
            <li>Reviewing trial requests and coordinating trial setup</li>
            <li>Providing, operating, and supporting the Lacteva service</li>
            <li>Authentication, security, and preventing misuse</li>
            <li>Troubleshooting, service reliability, backups, and recovery</li>
            <li>Maintaining auditability of actions taken in the platform</li>
            <li>Improving the service</li>
            <li>Complying with applicable legal obligations</li>
          </Ul>
          <P>
            We do not use your information for third-party advertising, and we
            do not use customer platform data to train machine-learning
            models.
          </P>
        </LegalSection>

        <LegalSection title="5. How information is shared">
          <P>Information may be shared with:</P>
          <Ul>
            <li>
              Service providers we use to operate the service — for example
              infrastructure and hosting providers, and the systems that
              receive and manage website enquiries on our behalf
            </li>
            <li>Communications providers used to send notifications you or a customer have set up</li>
            <li>Parties a customer has authorized</li>
            <li>Professional advisers, where appropriate</li>
            <li>Legal or regulatory authorities, where required by law</li>
            <li>
              Parties involved in a legitimate business transaction such as a
              financing, reorganization, or acquisition, where legally
              appropriate and subject to appropriate protections
            </li>
          </Ul>
        </LegalSection>

        <LegalSection title="6. Data retention">
          <P>
            We retain information for as long as reasonably necessary for the
            purposes described in this policy, including providing the
            service, maintaining security and business records, resolving
            disputes, and complying with applicable legal obligations. For
            information processed through the platform, retention may also
            depend on the customer relationship and applicable contractual
            arrangements.
          </P>
        </LegalSection>

        <LegalSection title="7. Security">
          <P>
            We use technical and organizational measures designed to protect
            information against unauthorized access, alteration, disclosure,
            loss, or destruction. In the Lacteva platform these include
            role-based access controls with granular permissions, isolation of
            each customer organization&apos;s data enforced at the database
            level, an append-only audit trail of changes, secure
            authentication, monitoring, and tested backup and recovery
            procedures. No method of transmission or storage is completely
            secure, and we cannot promise absolute security.
          </P>
        </LegalSection>

        <LegalSection title="8. Cookies">
          <P>
            This marketing website does not use analytics, advertising, or
            tracking cookies, and does not set cookies for its public pages.
            The separate Lacteva platform uses the technologies necessary to
            operate a secure signed-in service, such as session
            authentication.
          </P>
        </LegalSection>

        <LegalSection title="9. Your rights and choices">
          <P>
            Depending on applicable law, you may have rights in relation to
            your personal information, such as the right to request access,
            correction, or deletion, to withdraw consent where processing is
            based on consent, and to raise a complaint or grievance. To
            exercise a right, contact us using the details below; where the
            information was submitted by a Lacteva customer through the
            platform, we may refer your request to that customer, who controls
            the relationship.
          </P>
        </LegalSection>

        <LegalSection title="10. Children">
          <P>
            Lacteva is a business service. This website and the platform are
            not directed toward children, and we do not knowingly seek to
            collect children&apos;s personal information through this website.
          </P>
        </LegalSection>

        <LegalSection title="11. International processing">
          <P>
            Information may be processed in locations where{" "}
            <Placeholder>[LEGAL ENTITY NAME]</Placeholder>, its affiliates, or
            its service providers operate, subject to applicable law.
          </P>
        </LegalSection>

        <LegalSection title="12. Changes to this policy">
          <P>
            We may update this policy from time to time. The &quot;Last
            updated&quot; date at the top of this page shows when it last
            changed; material changes will be reflected on this page.
          </P>
        </LegalSection>

        <LegalSection title="13. Contact">
          <P>
            Questions about this policy or about how your information is
            handled can be sent to{" "}
            <Placeholder>[PRIVACY CONTACT EMAIL]</Placeholder> or by post to{" "}
            <Placeholder>[REGISTERED/BUSINESS ADDRESS]</Placeholder>.
          </P>
        </LegalSection>
      </LegalArticle>
    </Section>
  );
}
