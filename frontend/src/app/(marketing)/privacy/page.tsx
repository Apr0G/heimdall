import type { Metadata } from "next";

import { LegalPage } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Privacy Policy — Heimdall",
  description: "How Heimdall handles data.",
};

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" lastUpdated="July 2026">
      <p>
        This Privacy Policy explains how Heimdall (&ldquo;Heimdall,&rdquo;
        &ldquo;we,&rdquo; &ldquo;us&rdquo;) handles information when a practice
        uses the service.
      </p>

      <h2>1. Information we collect</h2>
      <ul>
        <li>
          <span className="text-foreground">Account information</span> — the
          email and practice details used to sign in.
        </li>
        <li>
          <span className="text-foreground">Claim documents</span> — the denial,
          claim, and clinical documents your practice uploads to process an
          appeal.
        </li>
        <li>
          <span className="text-foreground">Usage data</span> — basic logs
          needed to operate and secure the service (never document contents).
        </li>
      </ul>

      <h2>2. How we use information</h2>
      <p>
        We use uploaded documents solely to extract claim data, analyze the
        denial, and draft the appeal letter for your practice. We do not sell
        your data.
      </p>

      <h2>3. Protected health information (PHI)</h2>
      <p>
        Heimdall is built to handle healthcare data carefully: documents are
        encrypted in transit and at rest, identifiers such as member IDs are
        minimized, and logs never contain document text or patient content.
        Handling of PHI is governed by the agreement between your practice and
        Heimdall.
      </p>

      <h2>4. Sharing &amp; subprocessors</h2>
      <p>
        We use trusted infrastructure and AI subprocessors to run the service.
        We share only what is necessary to provide it, under appropriate
        confidentiality and data-protection terms.
      </p>

      <h2>5. Security</h2>
      <p>
        We use industry-standard safeguards including encryption, access
        controls, and audit logging. No system is perfectly secure, but we work
        to protect your data.
      </p>

      <h2>6. Retention</h2>
      <p>
        We retain documents and case data for as long as needed to provide the
        service and meet legal obligations, then delete or de-identify them.
      </p>

      <h2>7. Your choices</h2>
      <p>
        Your practice may request access to, correction of, or deletion of its
        data, subject to legal and contractual requirements.
      </p>

      <h2>8. Changes</h2>
      <p>
        We may update this policy; material changes will be communicated to your
        practice.
      </p>

      <h2>9. Contact</h2>
      <p>
        Questions about privacy? Email{" "}
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="underline hover:text-foreground"
        >
          {CONTACT_EMAIL}
        </a>
        .
      </p>
    </LegalPage>
  );
}
