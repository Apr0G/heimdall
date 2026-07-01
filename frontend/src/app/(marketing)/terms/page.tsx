import type { Metadata } from "next";

import { LegalPage } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Terms of Service — Heimdall",
  description: "The terms that govern use of Heimdall.",
};

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service" lastUpdated="July 2026">
      <p>
        These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of Heimdall
        (&ldquo;Heimdall,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;). By using the service, your
        practice agrees to these Terms.
      </p>

      <h2>1. The service</h2>
      <p>
        Heimdall helps healthcare practices analyze denied insurance claims and draft appeal
        letters. Heimdall is a drafting and estimation tool only; it does not submit appeals or
        guarantee any outcome.
      </p>

      <h2>2. Accounts</h2>
      <p>
        Accounts are provisioned by Heimdall. You are responsible for keeping your credentials
        secure and for all activity under your account.
      </p>

      <h2>3. Acceptable use</h2>
      <ul>
        <li>Use the service only for lawful purposes and for claims your practice is authorized to handle.</li>
        <li>Do not attempt to disrupt, reverse-engineer, or gain unauthorized access to the service.</li>
        <li>Do not upload content you do not have the right to submit.</li>
      </ul>

      <h2>4. AI-assisted output</h2>
      <p>
        Heimdall uses AI to estimate appeal success and to draft letters. Output may contain errors
        and must be reviewed by a qualified person before use. Heimdall is not a medical, legal, or
        billing advisor, and all clinical, financial, and submission decisions remain with your
        practice.
      </p>

      <h2>5. Intellectual property</h2>
      <p>
        Heimdall and its underlying software are owned by us. You retain rights to the documents you
        upload and the letters generated for your claims.
      </p>

      <h2>6. Disclaimers &amp; limitation of liability</h2>
      <p>
        The service is provided &ldquo;as is&rdquo; without warranties of any kind. To the maximum
        extent permitted by law, Heimdall is not liable for indirect or consequential damages, or
        for any denied, reduced, or unrecovered claim amounts.
      </p>

      <h2>7. Termination</h2>
      <p>
        Either party may terminate access at any time. Provisions that by their nature should
        survive termination will survive.
      </p>

      <h2>8. Changes</h2>
      <p>We may update these Terms; material changes will be communicated to your practice.</p>

      <h2>9. Contact</h2>
      <p>
        Questions about these Terms? Email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`} className="underline hover:text-foreground">
          {CONTACT_EMAIL}
        </a>
        .
      </p>
    </LegalPage>
  );
}
