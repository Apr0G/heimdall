// GENERATED from docs/policies/privacy-policy.md by scripts/legal-pages.mjs. Do not hand-edit the
// body: edit the Markdown (the retained policy record) and regenerate.
import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  description:
    "How Heimdall Claims collects, uses, shares and protects information.",
};

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy Policy"
      effective="October 19, 2026"
      lastUpdated="October 19, 2026"
    >
      <p>
        This Privacy Policy explains how Heimdall Claims, Inc.
        (&quot;Heimdall&quot;, &quot;we&quot;, &quot;us&quot;, &quot;our&quot;),
        a Delaware corporation, collects, uses, shares and protects information
        when you visit heimdallclaims.com, use the Heimdall application and API
        (together, the &quot;Service&quot;), fill in a form on our site, or
        communicate with us. It also explains, for transparency, how we handle
        the health information that healthcare practices entrust to us, even
        though that information is governed first by law and by our contracts
        with those practices.
      </p>
      <p>
        Please read this policy together with our{" "}
        <Link href="/terms">Terms of Service</Link> and our{" "}
        <Link href="/subprocessors">Subprocessors</Link> list. If you do not
        agree with this policy, please do not use the Service.
      </p>
      <h2 id="1-who-we-are-and-the-roles-we-play">
        1. Who we are and the roles we play
      </h2>
      <p>
        Heimdall is a software company. We provide a web-based tool that helps
        small United States healthcare practices check draft insurance claims
        for denial risk before submission, analyze claim denials, and draft
        appeal letters. We are not a healthcare provider, a health plan, a
        clearinghouse, a billing company, or a law firm.
      </p>
      <p>
        We handle information in two different roles, and the rules differ
        between them:
      </p>
      <ul>
        <li>
          <strong>As a business, for our own purposes.</strong> This covers
          information about visitors to our website, prospective customers who
          contact us, and the staff of practices who hold user accounts (for
          example their work email address and login activity). This policy is
          the main document that governs that information.
        </li>
        <li>
          <strong>
            As a business associate under HIPAA, on behalf of a practice.
          </strong>{" "}
          When a practice uploads claim documents, denial letters or clinical
          notes, those documents contain protected health information
          (&quot;PHI&quot;) about the practice&apos;s patients. Under the Health
          Insurance Portability and Accountability Act (&quot;HIPAA&quot;), the
          practice is the covered entity and Heimdall is its business associate.
          We process that PHI only as the practice instructs and as permitted by
          the Business Associate Agreement (&quot;BAA&quot;) between the
          practice and Heimdall. Where this policy and a BAA conflict with
          respect to PHI, the BAA controls.
        </li>
      </ul>
      <p>
        <strong>If you are a patient.</strong> Heimdall does not have a direct
        relationship with patients. Your healthcare provider decides what
        information to upload and is responsible for your privacy notices and
        for responding to your requests about your health records. Please direct
        any request about your health information to your provider. We will help
        the provider respond, as our BAA requires.
      </p>
      <h2 id="2-information-we-collect">2. Information we collect</h2>
      <h3 id="2-1-information-you-give-us-directly">
        2.1 Information you give us directly
      </h3>
      <ul>
        <li>
          <strong>&quot;Get started&quot; and contact requests.</strong> If you
          submit the form at /get-started, we collect your name, your work email
          address and the free-text description of your practice that you choose
          to write. If you email us, we collect your email address and whatever
          you include in the message. We ask you not to include any patient
          information in these messages.
        </li>
        <li>
          <strong>Account information.</strong> Heimdall accounts are created by
          invitation only. When Heimdall, at a practice&apos;s request, invites
          a member of the practice&apos;s staff, we record that person&apos;s
          full name, work email address, role within the practice (doctor or
          office manager), the practice they belong to, the time of their last
          sign-in, and the time of their last request (updated roughly once a
          minute while they use the Service, to enforce the inactivity timeout).
          Passwords and authenticator secrets are handled by our identity
          provider (Amazon Cognito). Heimdall never stores your password: when
          you sign in or change it, the password is passed to Cognito for
          verification and is not written to any log.
        </li>
        <li>
          <strong>Practice information.</strong> For each customer practice we
          record the practice name, National Provider Identifier (NPI), tax
          identification number, business address, and the version and date of
          the BAA the practice signed.
        </li>
        <li>
          <strong>Things you type into the Service.</strong> This includes notes
          you add when logging the outcome of an appeal, the reason you give
          when requesting that your own account be deactivated, and the edits
          you select when correcting a draft claim.
        </li>
        <li>
          <strong>Support and other communications.</strong> Records of your
          correspondence with us.
        </li>
      </ul>
      <h3 id="2-2-information-collected-automatically">
        2.2 Information collected automatically
      </h3>
      <p>
        When you use the website or the Service, our systems record technical
        information about the request. This includes:
      </p>
      <ul>
        <li>
          <strong>Network and device data.</strong> Your IP address, browser
          type and version (the &quot;user agent&quot; string), the date and
          time of the request, the page or API endpoint requested, the response
          status, and internal request identifiers. We do not collect precise
          geolocation and we do not fingerprint devices.
        </li>
        <li>
          <strong>Account activity (audit logs).</strong> For every login,
          logout, password change, authenticator reset, and every time an
          account views a case, downloads a document or letter, uploads a file,
          or changes account settings, we write an entry to an append-only audit
          log that records who did what, when, from which IP address and with
          which browser. These records exist because HIPAA requires us to be
          able to show who accessed health information. The application cannot
          edit or delete them (the database permissions forbid it); only the
          database owner could, and that access is itself logged by AWS. We keep
          them for at least six years. Audit entries never contain the contents
          of documents or patient data.
        </li>
        <li>
          <strong>Security and rate-limiting data.</strong> Our firewall (AWS
          WAF), network flow logs and rate limiter use your IP address and, for
          logged-in users, your account identifier to block abuse and
          brute-force login attempts. Rate-limit counters live for minutes to at
          most one day.
        </li>
        <li>
          <strong>Cookies and browser storage.</strong> Described in Section 7.
          We do not use advertising cookies, analytics trackers, pixels or any
          third-party tracking scripts on our site or in the Service.
        </li>
      </ul>
      <h3 id="2-3-health-information-uploaded-by-practices-phi">
        2.3 Health information uploaded by practices (PHI)
      </h3>
      <p>
        Practices upload PDF documents to the Service: draft or submitted claims
        (for example a CMS-1500 form), denial letters or explanations of
        benefits, clinical notes, and sometimes prior-authorization records or
        prior-treatment records. These documents routinely contain PHI such as
        patient names, dates of birth, dates of service, diagnosis and procedure
        codes, insurance member identifiers, claim numbers and clinical
        narratives.
      </p>
      <p>From these documents the Service produces and stores:</p>
      <ul>
        <li>
          extracted structured data (payer, plan type, claim number, denial
          codes, procedure and diagnosis codes, modifiers, dates of service,
          denial date, billed and denied amounts);
        </li>
        <li>
          the patient&apos;s initials and a keyed one-way hash of the insurance
          member identifier (we never store the member identifier itself in
          readable form);
        </li>
        <li>
          the name, size, type and cryptographic hash of each uploaded file as
          you supplied it (file names you choose may themselves contain patient
          names, so please name files carefully);
        </li>
        <li>
          the text extracted from each document (so that it does not have to be
          re-read each time);
        </li>
        <li>
          for appeals: a denial classification, an estimate of appeal success,
          the reasoning behind it, the recommended appeal level, any additional
          records the analysis suggests you obtain, the estimated appeal
          deadline, and the drafted appeal letter and its PDF;
        </li>
        <li>
          for pre-checks: a denial-risk report, proposed edits, and, if the
          practice chooses, a corrected copy of the claim PDF;
        </li>
        <li>
          the outcome the practice reports (whether you appealed; overturned,
          upheld, partial, withdrawn or pending; amount recovered; resolution
          date; notes; and who recorded it and when);
        </li>
        <li>
          a record of every AI model call made while processing the case (the
          model used, the prompt version, token counts, timing and success or
          failure) together with an archive of the exact text sent to and
          received from the model, kept for 30 days for quality and error
          investigation.
        </li>
      </ul>
      <p>Section 4 explains how this information is used and protected.</p>
      <h3 id="2-4-information-we-do-not-collect">
        2.4 Information we do not collect
      </h3>
      <p>
        We do not collect payment card details through the website or the
        Service (there is no online checkout). We do not collect Social Security
        numbers of account holders (a practice&apos;s tax identification number
        may be its owner&apos;s Social Security number if the practice is a sole
        proprietorship). We do not knowingly collect information from children
        (see Section 11). We do not buy information about you from data brokers.
      </p>
      <h2 id="3-how-we-use-information">3. How we use information</h2>
      <p>We use the information described in Section 2 to:</p>
      <ul>
        <li>
          provide, operate, secure and support the Service, including
          authenticating you, enforcing multi-factor authentication, signing you
          out after inactivity, and preventing abuse;
        </li>
        <li>
          respond to your &quot;get started&quot; request or other inquiry, set
          up your practice, and communicate with you about your account,
          security events and changes to the Service or to our terms;
        </li>
        <li>
          send the transactional emails the Service needs: account invitations
          with a temporary password, one-time codes for password reset and for
          recovering access when you lose your authenticator app, and an
          internal notice to Heimdall when a user asks to be deactivated. These
          emails never contain patient information;
        </li>
        <li>
          keep the audit logs that HIPAA requires and investigate security
          incidents;
        </li>
        <li>
          understand how the Service is used, in aggregate, so that we can fix
          problems and improve it (for example, how long processing takes, how
          often a step fails, and how much the AI processing costs per
          practice);
        </li>
        <li>
          comply with law, enforce our Terms of Service, and protect the rights,
          safety and property of Heimdall, our customers and others.
        </li>
      </ul>
      <p>
        We use PHI only to perform the Service for the practice that uploaded
        it, to carry out our obligations under the BAA, for our own management
        and administration and legal responsibilities as HIPAA permits, and,
        where the practice&apos;s BAA allows it, to create de-identified data as
        described in Section 5. We do not use PHI for marketing, and we do not
        sell PHI or any other personal information.
      </p>
      <h2 id="4-how-health-information-is-processed-and-protected">
        4. How health information is processed and protected
      </h2>
      <p>
        This section describes the data flow for PHI so that practices and their
        patients can see exactly what happens.
      </p>
      <ul>
        <li>
          <strong>Where it lives.</strong> All PHI is stored in Amazon Web
          Services (&quot;AWS&quot;) data centers in the United States
          (us-east-1 region): uploaded files, extracted text and model archives
          in Amazon S3; structured case data in an Amazon RDS PostgreSQL
          database. Everything is encrypted at rest with AWS Key Management
          Service keys that we control, and in transit with TLS. The database is
          not reachable from the public internet.
        </li>
        <li>
          <strong>Who processes it.</strong> Scanned PDFs are read with Amazon
          Textract (optical character recognition). Document text is then sent
          to a large language model (Anthropic&apos;s Claude) running inside
          Amazon Bedrock, which extracts data, classifies the denial, estimates
          appeal success, reviews the clinical documentation against the billed
          codes and drafts letters. These are AWS services covered by our
          Business Associate Agreement with AWS. AWS states that Amazon Bedrock
          does not use customer prompts or outputs to train its models and does
          not share them with model providers. Amazon Comprehend Medical is used
          only during the de-identification process described in Section 5. The
          complete list of vendors is on our{" "}
          <Link href="/subprocessors">Subprocessors</Link> page.
        </li>
        <li>
          <strong>What never happens.</strong> Our web front end, hosted by
          Vercel, serves only the application code. Documents and case data
          travel directly between your browser and our AWS infrastructure, and
          the session cookie that authorizes those requests is scoped to our
          API, so PHI does not pass through or rest on Vercel&apos;s servers. AI
          models are never called from your browser. Document contents and
          patient data are never written to application logs; our logging code
          strips identifiers defensively, and our error reporting withholds any
          message that could echo document contents.
        </li>
        <li>
          <strong>Who can see it.</strong> Only the staff of the practice that
          uploaded a case can view that case; every database query is scoped to
          the practice, and we test this. Heimdall&apos;s own staff hold
          administrator accounts that give a cross-practice view of account
          records (names, work email addresses, roles, status, last activity),
          pending deactivation requests and per-practice usage aggregates (case
          counts, billed and denied totals, AI processing cost); that view does
          not open a practice&apos;s cases, and every use of it is audit-logged.
          Heimdall personnel do not routinely access PHI. When access is
          necessary (for example, to investigate a processing failure at a
          practice&apos;s request) it is limited to what is needed and is itself
          recorded.
        </li>
        <li>
          <strong>How it is deleted.</strong> Temporary upload objects are
          deleted after one day. Model request and response archives are deleted
          after 30 days. Database backups are kept for 30 days. When a practice
          ends its relationship with us, we return or destroy its PHI as the BAA
          requires, including all stored versions of its files, and we confirm
          the destruction to the practice in writing and keep that confirmation
          as a compliance record. Audit logs, which contain no patient data, are
          retained (Section 8).
        </li>
      </ul>
      <h2 id="5-de-identified-data-and-improving-the-service">
        5. De-identified data and improving the Service
      </h2>
      <p>
        With a practice&apos;s written permission in its BAA (and only then), we
        may create de-identified data from completed appeal cases to evaluate
        and improve the Service, including the AI models and prompts behind it.
      </p>
      <p>Here is what that means in practice:</p>
      <ul>
        <li>
          <strong>What is included.</strong> Only text that our own system
          generated (the clinical summary, the appeal analysis and reasoning,
          and the drafted appeal letter), together with non-identifying
          structured fields such as payer name, plan type, the practice&apos;s
          state, dollar amounts, procedure and diagnosis codes, the year of
          service, and the reported outcome. The raw uploaded documents and the
          text extracted from them are never included.
        </li>
        <li>
          <strong>How identifiers are removed.</strong> We follow the HIPAA Safe
          Harbor standard (45 CFR 164.514(b)(2)). Every free-text field passes
          through three independent layers: a rule set written for this purpose,
          an open-source clinical de-identification model, and Amazon Comprehend
          Medical&apos;s PHI detection. Anything any layer finds is removed. A
          separate, broader scan then checks the result; if it finds anything
          that looks like an identifier, the export is aborted. Nothing in a
          de-identified record is derived from an identifier: each record gets a
          new random code, and the only link between that code and a patient is
          a table that never leaves our database. Dates are reduced to the year,
          ages over 89 are generalized, and initials, names, addresses, employer
          references and identification numbers are removed.
        </li>
        <li>
          <strong>Human review before use.</strong> Even after all of that, the
          output is treated as PHI and held in a quarantine area for up to 30
          days until a named reviewer has read it, checked it against the Safe
          Harbor &quot;no actual knowledge&quot; standard, and recorded their
          attestation and the file&apos;s cryptographic hash in an append-only
          release log. A corpus that is not reviewed and released simply
          expires.
        </li>
        <li>
          <strong>How we use and keep it.</strong> Released de-identified data
          is no longer PHI under HIPAA and may be retained indefinitely and used
          to measure, test and improve the Service. We do not sell de-identified
          data. If we ever share it with a research or technology partner, the
          recipient will be contractually prohibited from attempting to
          re-identify anyone.
        </li>
        <li>
          <strong>Opting out.</strong> A practice whose BAA does not permit
          de-identification is never included. A practice that is included may
          withdraw permission for future exports by amending its BAA; data
          already released cannot be recalled because it no longer identifies
          anyone.
        </li>
      </ul>
      <h2 id="6-how-we-share-information">6. How we share information</h2>
      <p>We share personal information only in the following circumstances:</p>
      <ul>
        <li>
          <strong>Service providers (subprocessors).</strong> Companies that
          host and operate the Service on our behalf: AWS (infrastructure,
          storage, databases, OCR, AI processing, identity, email, monitoring),
          Vercel (hosting of the web front end) and SMTP2GO (delivery of account
          emails to practice staff). Each is bound by contract to use the
          information only to provide its service to us. The current list, with
          what each one receives, is at{" "}
          <Link href="/subprocessors">/subprocessors</Link>. PHI goes only to
          subprocessors that have signed a Business Associate Agreement with us.
        </li>
        <li>
          <strong>Within your practice.</strong> Because all case data belongs
          to the practice, every authorized user of your practice can see the
          practice&apos;s cases. Heimdall&apos;s administrators see account
          records and usage aggregates across practices as described in Section
          4.
        </li>
        <li>
          <strong>Our own mailbox provider.</strong> The notification we receive
          when you submit the &quot;get started&quot; form, and operational
          alerts about the Service (which can name a staff email address when an
          account email bounces), are delivered to a Heimdall mailbox hosted by
          Google (Gmail). No patient data is ever sent there.
        </li>
        <li>
          <strong>Legal requirements.</strong> When we believe in good faith
          that disclosure is required by law, regulation, legal process or a
          governmental request, or is necessary to protect the rights, property
          or safety of Heimdall, our customers or the public. Where PHI is
          involved we will follow the BAA and HIPAA, which generally require
          that we notify the practice unless the law prohibits it.
        </li>
        <li>
          <strong>Business transfers.</strong> If Heimdall is involved in a
          merger, acquisition, financing, reorganization or sale of assets,
          information may be transferred as part of that transaction. Any
          successor will be bound by this policy and, for PHI, by the applicable
          BAAs.
        </li>
        <li>
          <strong>Professional advisers.</strong> Our lawyers, accountants,
          auditors and insurers, under confidentiality obligations.
        </li>
        <li>
          <strong>With your direction or consent.</strong>
        </li>
      </ul>
      <p>
        We do not sell personal information, we do not share it for
        cross-context behavioral advertising, and we do not allow third parties
        to collect information about you on our site for their own purposes.
      </p>
      <h2 id="7-cookies-and-browser-storage">7. Cookies and browser storage</h2>
      <p>
        We use a small number of first-party cookies that are necessary for the
        Service to work. We do not use third-party cookies, advertising cookies
        or analytics cookies.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Set by</th>
            <th scope="col">Purpose</th>
            <th scope="col">Readable by scripts</th>
            <th scope="col">Lifetime</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>hd_session</td>
            <td>Our API (api.heimdallclaims.com)</td>
            <td>
              Holds your signed session token after you sign in. Marked
              HttpOnly, Secure and SameSite=Lax so that scripts cannot read it
              and it is only sent to our API.
            </td>
            <td>No</td>
            <td>
              At most 60 minutes, and ended earlier after 15 minutes of
              inactivity or when you sign out.
            </td>
          </tr>
          <tr>
            <td>hd_authed</td>
            <td>Our web app</td>
            <td>
              A flag with the single value &quot;1&quot; that tells the web app
              you are signed in, so it can send you to the right page. Contains
              no token and no personal data. Sent to Vercel, which serves the
              web app.
            </td>
            <td>Yes</td>
            <td>Up to 60 minutes; cleared when you sign out.</td>
          </tr>
          <tr>
            <td>hd_theme</td>
            <td>Our web app</td>
            <td>
              Remembers whether you chose the light or dark theme so the correct
              icon and colors load. Sent to Vercel, which serves the web app.
            </td>
            <td>Yes</td>
            <td>One year.</td>
          </tr>
        </tbody>
      </table>
      <p>
        The web app also stores your theme preference in your browser&apos;s
        local storage. Fonts and all scripts are served from our own domain; no
        request is made to a font or script provider when you load a page.
      </p>
      <p>
        You can delete or block cookies in your browser settings. If you block
        the hd_session cookie you will not be able to sign in. Because we do not
        track visitors, we do not respond differently to &quot;Do Not
        Track&quot; or Global Privacy Control signals; there is no tracking to
        turn off.
      </p>
      <h2 id="8-how-long-we-keep-information">
        8. How long we keep information
      </h2>
      <table>
        <thead>
          <tr>
            <th scope="col">Information</th>
            <th scope="col">Retention</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>&quot;Get started&quot; and contact inquiries</td>
            <td>
              For as long as needed to respond and follow up, and then deleted
              on request or when no longer needed.
            </td>
          </tr>
          <tr>
            <td>Account information (name, work email, role)</td>
            <td>
              For the life of the account, and afterwards as long as audit log
              entries reference the account (at least six years), because
              deleting the account record would break the integrity of the audit
              trail. The account is deactivated and can no longer sign in.
            </td>
          </tr>
          <tr>
            <td>Practice information</td>
            <td>
              For the life of the customer relationship and for six years
              afterwards for compliance records.
            </td>
          </tr>
          <tr>
            <td>
              Uploaded documents, extracted text, case data, letters, risk
              reports, corrected claims
            </td>
            <td>
              For the life of the customer relationship, or sooner on the
              practice&apos;s written request to us (there is no self-service
              delete in the Service). Returned or destroyed at termination as
              the BAA requires.
            </td>
          </tr>
          <tr>
            <td>Temporary upload objects</td>
            <td>One day.</td>
          </tr>
          <tr>
            <td>Archives of AI model requests and responses</td>
            <td>30 days.</td>
          </tr>
          <tr>
            <td>Database backups</td>
            <td>30 days (rolling).</td>
          </tr>
          <tr>
            <td>Audit logs (who accessed what, when, from where)</td>
            <td>At least six years; append-only.</td>
          </tr>
          <tr>
            <td>Application and server logs (no document contents)</td>
            <td>
              30 to 90 days depending on the component. Network flow logs: 90
              days. AWS account activity logs (CloudTrail): seven years in
              write-protected storage, plus a one-year searchable copy.
            </td>
          </tr>
          <tr>
            <td>De-identified quarantine exports</td>
            <td>30 days unless reviewed and released.</td>
          </tr>
          <tr>
            <td>Released de-identified data</td>
            <td>Indefinitely (it is no longer PHI).</td>
          </tr>
          <tr>
            <td>Email delivery records held by our email providers</td>
            <td>
              Per each provider&apos;s standard retention for delivery metadata.
            </td>
          </tr>
        </tbody>
      </table>
      <h2 id="9-security">9. Security</h2>
      <p>
        We built the Service for health information from the start. Current
        safeguards include: encryption of all data at rest with customer-managed
        keys and in transit with TLS; a private database with no public network
        access; mandatory multi-factor authentication (an authenticator app) and
        strong password rules for every account; automatic sign-out after 15
        minutes of inactivity; server-side revocation of sessions on logout,
        password change or account deactivation; role-based access controls;
        append-only audit logs of every access to health information;
        practice-level isolation enforced on every database query and verified
        by automated tests; a web application firewall and rate limiting; a
        strict Content Security Policy that prevents scripts from third-party
        origins and limits where your browser may send data; secrets kept in a
        managed secrets store rather than in code; automated dependency, secret
        and static-analysis scanning on every code change; and security
        monitoring and alerting across our AWS account.
      </p>
      <p>
        No system can be guaranteed to be perfectly secure. If we discover a
        breach of unsecured PHI we will notify the affected practice without
        unreasonable delay and in any case within 60 days of discovery, as HIPAA
        and our BAA require, with the information the practice needs to meet its
        own notification duties. If a security incident affects personal
        information for which we are responsible directly (for example, contact
        details of a prospective customer), we will notify affected individuals
        and regulators as applicable law requires.
      </p>
      <p>
        If you believe you have found a security vulnerability in the Service,
        please email us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> with enough
        detail for us to reproduce it. We ask that you do not access or modify
        data that is not yours and that you give us a reasonable time to fix the
        issue before disclosing it publicly.
      </p>
      <h2 id="10-your-choices-and-rights">10. Your choices and rights</h2>
      <h3 id="10-1-account-holders">10.1 Account holders</h3>
      <p>
        Your account belongs to your practice. You can change your password at
        any time from the Settings page, and you can reset your authenticator
        there (we email you a code, sign you out everywhere, and you enroll a
        new authenticator at your next sign-in). To correct your name or role,
        or to have your account deactivated, your practice emails us and we make
        the change; you can also file a deactivation request yourself from the
        Settings page, which Heimdall reviews with your practice. Deactivation
        stops all access immediately. For the reasons in Section 8, the account
        record and audit entries are retained after deactivation.
      </p>
      <h3 id="10-2-prospective-customers-and-website-visitors">
        10.2 Prospective customers and website visitors
      </h3>
      <p>
        If you have contacted us and would like us to delete your contact
        details or stop contacting you, email us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and we will do
        so unless we need the information for a legitimate business or legal
        reason, which we will explain.
      </p>
      <h3 id="10-3-patients">10.3 Patients</h3>
      <p>
        Please contact your healthcare provider. Requests to access, correct,
        restrict or obtain an accounting of disclosures of your health records
        are handled by the provider under HIPAA, and we support the provider in
        fulfilling them.
      </p>
      <h3 id="10-4-rights-under-united-states-state-privacy-laws">
        10.4 Rights under United States state privacy laws
      </h3>
      <p>
        Depending on where you live, state privacy laws (for example in
        California, Colorado, Connecticut, Virginia, Texas, Oregon and others)
        may give you rights to know what personal information we hold about you,
        to access it in a portable format, to correct it, to delete it, to opt
        out of its sale, sharing for targeted advertising, or use in profiling
        that produces legal or similarly significant effects, and not to be
        discriminated against for exercising those rights. Many of those laws do
        not apply to PHI governed by HIPAA, to information about employees and
        business contacts, or to businesses of our size; but we will honor these
        requests from any United States resident regardless of whether the law
        technically requires it.
      </p>
      <p>
        To exercise a right, email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. We will need to
        verify that you are the person the information is about (usually by
        confirming control of the email address on record). You may use an
        authorized agent; we will ask for proof of the agent&apos;s authority.
        We will respond within 45 days, or tell you if we need more time. If we
        decline a request we will tell you why, and you may appeal by replying
        to our response.
      </p>
      <p>
        For the avoidance of doubt: we do not sell personal information; we do
        not share it for cross-context behavioral advertising; we do not use it
        for automated decisions that produce legal or similarly significant
        effects about individuals; and we do not collect personal information
        from consumers for those purposes. The categories of personal
        information we collect, the sources, the purposes and the categories of
        recipients are described in Sections 2, 3 and 6 of this policy, which
        also serves as our notice at collection.
      </p>
      <h2 id="11-children">11. Children</h2>
      <p>
        The website and the Service are intended for healthcare professionals
        and are not directed to children. We do not knowingly collect personal
        information directly from anyone under 18. Documents uploaded by a
        practice may relate to pediatric patients; that information is PHI
        handled on the practice&apos;s behalf as described in Section 4. If you
        believe a child has provided us personal information directly, contact
        us and we will delete it.
      </p>
      <h2 id="12-where-information-is-processed-users-outside-the-united-states">
        12. Where information is processed; users outside the United States
      </h2>
      <p>
        Heimdall operates in the United States and stores and processes
        information in the United States. The Service is designed for United
        States healthcare practices and United States insurance claims. If you
        access the website from outside the United States, you understand that
        your information will be transferred to and processed in the United
        States, where privacy laws may differ from those of your country.
      </p>
      <h2 id="13-communications-from-us">13. Communications from us</h2>
      <p>
        We send the emails needed to run your account (invitations, one-time
        codes, and any security notice we may need to send) and we reply to the
        inquiries you send us. We do not send marketing newsletters. If we ever
        introduce marketing email, we will ask for your consent first and every
        message will include a way to unsubscribe. Account and security emails
        cannot be opted out of while your account is active, because they are
        how the Service works.
      </p>
      <h2 id="14-links-and-third-party-sites">
        14. Links and third-party sites
      </h2>
      <p>
        Our site and the Service may link to third-party resources, for example
        payer websites, CMS reference pages or regulatory texts. Those sites
        have their own privacy practices and we are not responsible for them.
      </p>
      <h2 id="15-changes-to-this-policy">15. Changes to this policy</h2>
      <p>
        We will update this policy when our practices change. The &quot;Last
        updated&quot; date at the top tells you when. For material changes
        affecting account holders, we will give notice through the Service or by
        email to the practice&apos;s designated contact at least 30 days before
        the change takes effect, unless a shorter period is required by law.
        Earlier versions are retained in our records and are available on
        request.
      </p>
      <h2 id="16-contact-us">16. Contact us</h2>
      <p>Heimdall Claims, Inc., a Delaware corporation.</p>
      <p>
        Email: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Our
        postal address is available on request by email.
      </p>
      <p>
        Privacy inquiries, requests under Section 10, security reports and
        HIPAA-related questions should all be sent to that address with a
        subject line that says what the message is about. If you are a practice
        with a BAA and need to report a suspected incident, please mark the
        subject &quot;Security incident&quot; so that it is handled first.
      </p>
    </LegalPage>
  );
}
