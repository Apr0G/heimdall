// GENERATED from docs/policies/subprocessors.md by scripts/legal-pages.mjs. Do not hand-edit the
// body: edit the Markdown (the retained policy record) and regenerate.
import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  description:
    "The third-party service providers Heimdall Claims uses and what each one receives.",
};

export default function SubprocessorsPage() {
  return (
    <LegalPage
      title="Subprocessors"
      effective="October 19, 2026"
      lastUpdated="October 19, 2026"
    >
      <p>
        This page lists the third-party service providers
        (&quot;subprocessors&quot;) that Heimdall Claims, Inc. uses to deliver
        the Service, what each one does, and what information it receives. We
        publish it so that customer practices and their compliance officers can
        see the complete data flow. It supplements our{" "}
        <Link href="/privacy">Privacy Policy</Link> and{" "}
        <Link href="/terms">Terms of Service</Link>.
      </p>
      <p>
        Every subprocessor that handles protected health information
        (&quot;PHI&quot;) has signed a Business Associate Agreement
        (&quot;BAA&quot;) with us. Subprocessors that do not handle PHI are
        contractually limited to using the data they receive only to provide
        their service to us.
      </p>
      <h2 id="subprocessors-that-handle-phi">Subprocessors that handle PHI</h2>
      <p>
        All of the following are services of Amazon Web Services, Inc.
        (&quot;AWS&quot;), operated in the United States (us-east-1 region)
        under our AWS Business Associate Agreement. Our AWS account is
        configured so that these services are used only by our own systems;
        access by AWS personnel is governed by our AWS Business Associate
        Agreement.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">AWS service</th>
            <th scope="col">What it does for Heimdall</th>
            <th scope="col">Data it handles</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Amazon S3</td>
            <td>
              Stores uploaded PDF documents, text extracted from them, corrected
              claim files, the archives of AI model requests and responses (30
              days), and de-identified exports
            </td>
            <td>PHI at rest, encrypted with keys we control</td>
          </tr>
          <tr>
            <td>Amazon RDS (PostgreSQL)</td>
            <td>
              The database holding practices, users, cases, extracted data,
              analyses, letters, risk reports, outcomes and the append-only
              audit log
            </td>
            <td>PHI at rest, encrypted; not reachable from the internet</td>
          </tr>
          <tr>
            <td>Amazon ECS on AWS Fargate</td>
            <td>
              Runs the Heimdall API and the one-off operational tasks
              (migrations, data disposal, de-identification)
            </td>
            <td>PHI in memory while a case is processed</td>
          </tr>
          <tr>
            <td>Amazon Textract</td>
            <td>Optical character recognition of scanned PDF documents</td>
            <td>Scanned document images and the text read from them</td>
          </tr>
          <tr>
            <td>Amazon Bedrock (Anthropic Claude model)</td>
            <td>
              Extracts structured data, classifies denials, estimates appeal
              success, reviews documentation against billed codes, drafts appeal
              letters
            </td>
            <td>
              Document text and the model&apos;s output. AWS states that Bedrock
              does not use prompts or outputs to train models or share them with
              model providers
            </td>
          </tr>
          <tr>
            <td>Amazon Comprehend Medical</td>
            <td>
              Detects remaining identifiers during the de-identification process
              (Section 5 of the Privacy Policy)
            </td>
            <td>Heimdall-generated text being de-identified</td>
          </tr>
          <tr>
            <td>AWS Key Management Service</td>
            <td>Holds the encryption keys that protect everything above</td>
            <td>Keys only</td>
          </tr>
          <tr>
            <td>Amazon CloudWatch</td>
            <td>Application and infrastructure logs and alarms</td>
            <td>
              Technical logs: request paths, status codes, record identifiers
              and timings. Document contents and patient data are never written
              to logs
            </td>
          </tr>
          <tr>
            <td>AWS CloudTrail, GuardDuty, WAF, VPC Flow Logs</td>
            <td>
              Account audit trail, threat detection, web application firewall,
              network logs
            </td>
            <td>
              Security telemetry including IP addresses and request metadata
            </td>
          </tr>
          <tr>
            <td>AWS Secrets Manager</td>
            <td>
              Stores database credentials and other secrets used by the Service
            </td>
            <td>Credentials only</td>
          </tr>
        </tbody>
      </table>
      <h2 id="subprocessors-that-do-not-handle-phi">
        Subprocessors that do not handle PHI
      </h2>
      <table>
        <thead>
          <tr>
            <th scope="col">Provider</th>
            <th scope="col">Location</th>
            <th scope="col">What it does for Heimdall</th>
            <th scope="col">Data it handles</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Amazon Cognito (AWS)</td>
            <td>United States</td>
            <td>
              Identity provider for practice staff: sign-in, passwords,
              multi-factor authentication
            </td>
            <td>
              Account holders&apos; email addresses, authentication secrets and
              sign-in events. No patient data
            </td>
          </tr>
          <tr>
            <td>Amazon SES and Amazon SNS (AWS)</td>
            <td>United States</td>
            <td>
              Email delivery (SES, as a fallback provider when enabled) and
              internal notifications (SNS): &quot;get started&quot; requests are
              forwarded to us; operational alarms
            </td>
            <td>
              Prospect name, work email and message from the &quot;get
              started&quot; form; alarm and bounce notifications naming staff
              email addresses
            </td>
          </tr>
          <tr>
            <td>Amazon ElastiCache (AWS)</td>
            <td>United States</td>
            <td>Rate-limiting counters</td>
            <td>
              IP addresses and account identifiers as counter keys, held for
              minutes to one day
            </td>
          </tr>
          <tr>
            <td>AWS Lambda (AWS)</td>
            <td>United States</td>
            <td>
              Sends account invitation and password-reset emails on behalf of
              Cognito
            </td>
            <td>
              Staff email address and the one-time temporary password or code
            </td>
          </tr>
          <tr>
            <td>Vercel, Inc.</td>
            <td>United States</td>
            <td>
              Hosts and serves the Heimdall web front end (the application code
              and public pages)
            </td>
            <td>
              Standard web-server request logs: IP address, browser user agent,
              requested page, timestamp; and the hd_authed and hd_theme cookies
              (a signed-in flag and your theme choice: no token, no PHI). PHI
              does not pass through Vercel: case data travels directly between
              the browser and our AWS API, and the session cookie is scoped to
              the API host
            </td>
          </tr>
          <tr>
            <td>SMTP2GO (SMTP2GO Limited)</td>
            <td>United States and New Zealand</td>
            <td>
              Active transactional email provider for account emails to practice
              staff: invitations with temporary passwords, password-reset codes,
              authenticator-recovery codes; and the internal
              deactivation-request notice to Heimdall
            </td>
            <td>
              Staff email address and the message contents listed. Never patient
              data, by design and by code-level rule
            </td>
          </tr>
          <tr>
            <td>Google LLC (Gmail)</td>
            <td>United States</td>
            <td>
              Hosts the Heimdall mailbox that receives the &quot;get
              started&quot; notification and operational alert and bounce
              notices
            </td>
            <td>
              Prospect name, work email and message; staff email addresses named
              in bounce notices. Never patient data
            </td>
          </tr>
        </tbody>
      </table>
      <h2 id="reference-data-sources-not-subprocessors">
        Reference data sources (not subprocessors)
      </h2>
      <p>
        The Service downloads public reference tables published by the Centers
        for Medicare and Medicaid Services (the NCCI procedure-to-procedure and
        Medically Unlikely Edit tables). No customer data is sent to CMS.
      </p>
      <h2 id="changes-to-this-list">Changes to this list</h2>
      <p>
        We update this page before we start using a new subprocessor that will
        handle customer data, or when we replace one. Customers with a BAA may
        ask to be notified of such changes by email by writing to{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. If a Customer
        reasonably objects to a new subprocessor on data-protection grounds and
        we cannot offer an alternative, the Customer may terminate the affected
        service and receive a refund of prepaid, unused fees.
      </p>
    </LegalPage>
  );
}
