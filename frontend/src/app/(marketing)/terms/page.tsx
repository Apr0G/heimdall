// GENERATED from docs/policies/terms-of-service.md by scripts/legal-pages.mjs. Do not hand-edit the
// body: edit the Markdown (the retained policy record) and regenerate.
import type { Metadata } from "next";
import Link from "next/link";

import { LegalPage } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  description:
    "The terms that govern use of the Heimdall Claims website and service.",
};

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of Service"
      effective="October 19, 2026"
      lastUpdated="October 19, 2026"
    >
      <p>
        These Terms of Service (the &quot;Terms&quot;) are a legal agreement
        between Heimdall Claims, Inc., a Delaware corporation
        (&quot;Heimdall&quot;, &quot;we&quot;, &quot;us&quot;, &quot;our&quot;),
        and you. They govern your access to and use of the website at
        heimdallclaims.com, the Heimdall web application and API, and any
        related content, documentation and services we provide (together, the
        &quot;Service&quot;).
      </p>
      <p>
        <strong>
          Please read these Terms carefully. They include a binding arbitration
          clause and a class-action waiver (Section 17), disclaimers of
          warranties (Section 14) and limitations of our liability (Section 15).
          By visiting the website, submitting a form, signing in, or otherwise
          using the Service, you agree to these Terms. If you are using the
          Service on behalf of a healthcare practice or other organization, you
          represent that you have authority to bind that organization, and
          &quot;you&quot; includes that organization.
        </strong>
      </p>
      <h2 id="1-parties-agreements-and-order-of-precedence">
        1. Parties, agreements and order of precedence
      </h2>
      <ul>
        <li>
          <strong>&quot;Customer&quot;</strong> means the healthcare practice or
          other organization that has entered into an agreement with Heimdall to
          use the Service.
        </li>
        <li>
          <strong>&quot;Authorized User&quot;</strong> means an individual whom
          Heimdall, at a Customer&apos;s request, has invited to use the Service
          under the Customer&apos;s account, such as a physician or office
          manager.
        </li>
        <li>
          <strong>&quot;Visitor&quot;</strong> means anyone who browses the
          public pages of the website without signing in.
        </li>
        <li>
          <strong>&quot;Customer Content&quot;</strong> means all documents,
          data and other material that a Customer or its Authorized Users upload
          to or enter in the Service, and all output the Service generates from
          that material for the Customer (extracted data, analyses, risk
          reports, drafted letters, corrected claim files and outcome records).
        </li>
        <li>
          <strong>&quot;Order Form&quot;</strong> and{" "}
          <strong>&quot;Service Agreement&quot;</strong> mean any written
          agreement (including a quote, order form, subscription agreement or
          master services agreement) signed or accepted by Customer and Heimdall
          that describes the Service, fees and other commercial terms.
        </li>
        <li>
          <strong>&quot;BAA&quot;</strong> means the Business Associate
          Agreement between Customer and Heimdall under HIPAA.
        </li>
      </ul>
      <p>
        The Service is built to process protected health information
        (&quot;PHI&quot;).{" "}
        <strong>
          A Customer may not upload any PHI until a BAA is in place between the
          Customer and Heimdall.
        </strong>{" "}
        If there is a conflict among the documents that govern your use of the
        Service, the order of precedence is: (1) the BAA, with respect to PHI;
        (2) the Service Agreement or Order Form; (3) these Terms; (4) our{" "}
        <Link href="/privacy">Privacy Policy</Link> and any other policy
        referenced here. Terms printed on a Customer purchase order or similar
        document have no effect.
      </p>
      <h2 id="2-eligibility-accounts-and-security">
        2. Eligibility, accounts and security
      </h2>
      <ul>
        <li>
          <strong>Who may use the Service.</strong> The Service is intended for
          healthcare practices located in the United States that bill United
          States payers, and for their workforce. You must be at least 18 years
          old. You may use the Service only in connection with claims for
          services that your practice actually furnished and is authorized to
          bill.
        </li>
        <li>
          <strong>Invitation only.</strong> There is no self-service sign-up.
          Accounts are created when Heimdall, at the Customer&apos;s direction,
          invites a person by email. Each Authorized User receives a temporary
          password by email, valid for 7 days (ask us to re-send it if it
          expires), and must set a new password and enroll an authenticator app
          for multi-factor authentication on first sign-in. Multi-factor
          authentication is mandatory and cannot be disabled.
        </li>
        <li>
          <strong>Your credentials are yours alone.</strong> Do not share your
          account, password or authenticator with anyone, and do not use anyone
          else&apos;s. Each person who uses the Service must have their own
          account, so that the audit trail HIPAA requires is accurate. You are
          responsible for everything done under your account until you notify us
          that it may have been compromised.
        </li>
        <li>
          <strong>Sessions.</strong> For security, sessions end after 15 minutes
          of inactivity and in any event within 60 minutes, after which you must
          sign in again. Signing out, changing your password, resetting your
          authenticator or being deactivated ends every session of your account.
        </li>
        <li>
          <strong>Roles and the Customer&apos;s control.</strong> Accounts
          belong to the Customer, not to the individual. Heimdall, at the
          Customer&apos;s direction, invites, deactivates and reactivates
          Authorized Users and decides deactivation requests; Authorized Users
          may request their own deactivation from the Settings page. Customer is
          responsible for keeping its roster of Authorized Users current,
          including telling us promptly to deactivate anyone who leaves the
          practice. Heimdall&apos;s staff hold administrator accounts with a
          cross-practice view of account records and usage aggregates, as
          described in the Privacy Policy; that view does not open a
          Customer&apos;s cases and is audit-logged.
        </li>
        <li>
          <strong>Lost authenticator and forgotten password.</strong> We provide
          self-service recovery flows that send one-time codes to the email
          address on your account. A code expires after 10 minutes and is
          invalidated after 5 wrong attempts. These are the most sensitive part
          of the Service; keep control of your work email, and tell us
          immediately if you receive a code you did not request.
        </li>
        <li>
          <strong>Notify us of problems.</strong> Tell us promptly at{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> if you suspect
          unauthorized access to your account or to the Service, or if you
          notice an error in how the Service handled a case.
        </li>
      </ul>
      <h2 id="3-what-the-service-does-and-what-it-does-not-do">
        3. What the Service does, and what it does not do
      </h2>
      <h3 id="3-1-features">3.1 Features</h3>
      <ul>
        <li>
          <strong>Pre-check.</strong> You upload a draft claim and the
          supporting clinical notes before the claim is sent to a payer. The
          Service runs the claim&apos;s codes through the Centers for Medicare
          and Medicaid Services (&quot;CMS&quot;) National Correct Coding
          Initiative (&quot;NCCI&quot;) procedure-to-procedure bundling edits
          and Medically Unlikely Edits, and an AI model compares the clinical
          documentation to the billed codes. The result is a denial-risk report
          that lists findings, the denial each finding predicts, and suggested
          fixes.
        </li>
        <li>
          <strong>Corrected claim.</strong> For a draft claim that was produced
          digitally (not scanned), you may select some or all of the suggested
          edits and the Service will produce a corrected copy of the claim PDF
          with those edits applied in place. No AI model is involved in this
          step; the change is purely mechanical, and the Service re-reads the
          result to verify it. For a fillable claim form, the Service edits the
          form fields. For scanned claims you receive the list of edits only.
        </li>
        <li>
          <strong>Appeals.</strong> After a denial, you upload the denial or
          explanation of benefits, the claim and the clinical notes. The Service
          extracts the structured data, classifies the denial, states whether it
          appears appealable and why, estimates the likelihood of a successful
          appeal, recommends an appeal level, and drafts an appeal letter that
          you can review, download as a PDF, and send. If the analysis indicates
          that additional records (for example a prior authorization) would
          strengthen the appeal, you may upload them and the Service will draft
          a new version of the letter.
        </li>
        <li>
          <strong>Outcomes and dashboard.</strong> After you submit an appeal
          you mark it as submitted and later record the payer&apos;s decision
          and any amount recovered. The dashboard shows win rates and recovered
          amounts computed from the outcomes your practice reported, and reminds
          you about appeals whose outcome has not been recorded.
        </li>
      </ul>
      <h3 id="3-2-limits-of-the-service">3.2 Limits of the Service</h3>
      <p>
        Heimdall is a drafting, screening and estimation tool. It is important
        that you understand what it is not:
      </p>
      <ul>
        <li>
          <strong>Heimdall does not submit anything.</strong> It does not
          transmit claims or appeals to payers, does not connect to
          clearinghouses, electronic health record systems or payer portals, and
          has no relationship with any payer. You submit claims and appeals
          yourself, through your own channels, after your own review.
        </li>
        <li>
          <strong>
            Heimdall is not a medical, legal, coding, billing or compliance
            advisor
          </strong>
          , and it is not a billing company, a clearinghouse, a health plan, a
          utilization review agent or a medical device. Nothing produced by the
          Service is medical advice, legal advice, coding advice or a
          determination of coverage or medical necessity. Every clinical,
          coding, financial and submission decision remains with the Customer
          and its licensed and qualified personnel.
        </li>
        <li>
          <strong>Heimdall does not guarantee any outcome.</strong> A claim that
          passes a pre-check may be denied; a flagged claim may be paid; an
          appeal estimated as likely to succeed may be upheld; and a drafted
          letter may be rejected. Payers apply their own rules, which change and
          which the Service may not know.
        </li>
        <li>
          <strong>The pre-check baseline is Medicare.</strong> The deterministic
          edits are the CMS NCCI practitioner edits, refreshed monthly from the
          quarterly tables CMS publishes; each report records which edition was
          applied. A payer may be using a different edition, apply additional or
          different edits, or follow its own policies. The AI documentation
          review is an opinion generated by a model, not a coding determination.
        </li>
        <li>
          <strong>Deadline information is an estimate.</strong> Appeal deadlines
          shown by the Service are calculated from typical rules for the type of
          plan detected (currently 120 days from the denial date for Medicare
          and 60 days otherwise), and the detected plan type may itself be
          wrong. Your contract with the payer, the denial notice and applicable
          law control. Verify every deadline yourself.
        </li>
        <li>
          <strong>Statistics describe your own reported data.</strong> Win rates
          and recovered amounts reflect only what your practice entered.
        </li>
      </ul>
      <h2 id="4-artificial-intelligence-disclosure-and-your-obligations">
        4. Artificial intelligence: disclosure and your obligations
      </h2>
      <p>
        The Service uses artificial intelligence. This section explains how, and
        what we need from you.
      </p>
      <ul>
        <li>
          <strong>What runs.</strong> Document text is processed by a large
          language model (currently Anthropic&apos;s Claude, operated through
          Amazon Bedrock inside our AWS environment) to extract data, classify
          denials, estimate success, review documentation against codes and
          draft letters. Scanned documents are read with Amazon Textract. The
          NCCI bundling and unit checks and the corrected-claim editing are
          ordinary deterministic software, not AI. Models are called only from
          our servers, never from your browser, and every model call is recorded
          with the model and prompt version used. We may change or upgrade the
          models, prompts and vendors we use.
        </li>
        <li>
          <strong>AI output can be wrong.</strong> Language models can misread
          documents, miss information, state things that are not supported by
          the documents, apply rules incorrectly, and produce confident-sounding
          errors. Estimates of appeal success are probabilistic, not
          predictions, and are not based on your payer&apos;s actual decision
          data. Output quality depends on the legibility and completeness of
          what you upload; when a document is long, the Service may truncate
          part of it before analysis, and we record that internally for every
          model call.
        </li>
        <li>
          <strong>A qualified person must review everything before use.</strong>{" "}
          You agree that no risk report, suggested edit, corrected claim,
          analysis, estimate or letter produced by the Service will be relied
          on, submitted to a payer or otherwise acted on until it has been
          reviewed and approved by a person with the training and authority to
          make that decision for your practice. Drafted letters in particular
          must be read in full, corrected where necessary, and signed by an
          authorized representative of the practice before being sent.
        </li>
        <li>
          <strong>No emergency or clinical use.</strong> The Service is not
          designed for, and must not be used for, decisions about patient care,
          emergencies, or any purpose other than administrative review of
          claims.
        </li>
        <li>
          <strong>No payer or adverse-determination use.</strong> You may not
          use the Service to make or support a coverage decision, utilization
          review, or any adverse benefit determination against a patient or
          provider.
        </li>
        <li>
          <strong>Reference data notices.</strong> The Service refers to
          procedure codes contained in your own documents and in the CMS NCCI
          tables. CPT is a registered trademark of the American Medical
          Association. The Service does not provide, license or display the CPT
          code set or its descriptors; you are responsible for holding any
          licenses your own use of the CPT code set requires. NCCI edit tables
          and Claim Adjustment Reason Code descriptions are public reference
          data and are provided as-is.
        </li>
      </ul>
      <h2 id="5-customer-responsibilities">5. Customer responsibilities</h2>
      <p>In addition to Section 4, Customer agrees that it will:</p>
      <ul>
        <li>
          <strong>Have the right to upload what it uploads.</strong> Customer
          will upload only documents relating to patients the practice has
          treated and claims the practice is authorized to bill, and only after
          a BAA is in place. Customer is responsible for having all patient
          authorizations, notices and consents that its own use of the Service
          requires and for complying with HIPAA&apos;s minimum-necessary
          standard.
        </li>
        <li>
          <strong>Keep uploads accurate and lawful.</strong> Documents must be
          genuine, unaltered records of services actually furnished and
          documented. Customer will not upload content that is false,
          misleading, fraudulent or that it has no right to use, and will not
          upload files containing malware or anything designed to interfere with
          the Service.
        </li>
        <li>
          <strong>Own every claim and appeal it submits.</strong> A corrected
          claim produced by the Service reflects edits that Customer selected.
          Customer is solely responsible for ensuring that any claim or appeal
          it submits to a payer is accurate, complete, supported by the medical
          record and compliant with federal and state law, payer contracts and
          coding rules, including the False Claims Act and anti-kickback and
          billing-integrity laws. Heimdall does not and cannot verify that a
          code or modifier is supported by the documentation.
        </li>
        <li>
          <strong>Review, decide and keep records.</strong> Customer will review
          all output as described in Section 4, make its own decisions about
          what to submit, and keep its own copies of claims, appeals and
          supporting records as its record-retention duties require. The Service
          is not a system of record or a backup.
        </li>
        <li>
          <strong>
            Report outcomes truthfully and keep its roster current.
          </strong>{" "}
          Outcome data you enter should be accurate. Promptly deactivate
          Authorized Users who no longer need access.
        </li>
        <li>
          <strong>Protect its own environment.</strong> Customer is responsible
          for the security of its devices, networks, email accounts and
          browsers, and for compliance with its own policies when using the
          Service from any location.
        </li>
        <li>
          <strong>Comply with law.</strong> Customer will use the Service in
          compliance with all applicable laws and regulations, including HIPAA,
          state privacy and health-information laws, and the rules of the payers
          it bills.
        </li>
      </ul>
      <h2 id="6-acceptable-use">6. Acceptable use</h2>
      <p>You will not, and will not permit anyone to:</p>
      <ul>
        <li>
          access or use the Service without a valid account, share credentials,
          or attempt to bypass authentication, multi-factor authentication,
          session limits, rate limits or any other security control;
        </li>
        <li>
          access, attempt to access, or probe for another practice&apos;s data,
          or test the Service&apos;s security without our prior written
          permission;
        </li>
        <li>
          upload or transmit viruses, malicious code, or anything designed to
          disrupt, overload or damage the Service or its infrastructure;
        </li>
        <li>
          use automated means (bots, scrapers, scripts) to access the Service or
          to extract data from it, other than through functionality we provide;
        </li>
        <li>
          copy, modify, translate, create derivative works of, reverse engineer,
          decompile or disassemble the Service, or attempt to discover its
          source code, prompts, models or underlying algorithms, except to the
          extent applicable law prohibits this restriction;
        </li>
        <li>
          rent, lease, sell, sublicense, resell, time-share or otherwise make
          the Service available to any third party, or use it to build a
          competing product or to train a competing model;
        </li>
        <li>
          use the Service for any purpose other than the administrative review
          of your own practice&apos;s claims, including for any unlawful,
          fraudulent, deceptive or abusive purpose, or in violation of any payer
          contract;
        </li>
        <li>
          upload PHI of individuals you have no treatment or billing
          relationship with, or upload any content for which you lack authority;
        </li>
        <li>
          remove or alter any proprietary notice in the Service or in its
          output; or
        </li>
        <li>interfere with any other user&apos;s use of the Service.</li>
      </ul>
      <p>
        We may investigate suspected violations and may suspend or terminate
        access, remove content, and involve law enforcement where appropriate.
      </p>
      <h2 id="7-fees-and-payment">7. Fees and payment</h2>
      <p>
        Browsing the website costs nothing. Use of the Service by a Customer is
        subject to the fees set out in the Customer&apos;s Order Form or Service
        Agreement, which may include subscription fees, usage-based fees or
        both. Unless that agreement says otherwise: fees are stated and payable
        in United States dollars; invoices are due within 30 days of the invoice
        date; amounts not paid when due may accrue interest at the lesser of 1.5
        percent per month or the maximum rate permitted by law, and we may
        suspend the Service after notice; fees are exclusive of taxes, and
        Customer is responsible for all sales, use and similar taxes other than
        taxes on our income; and fees are non-refundable except as expressly
        stated in the agreement or required by law. We do not collect payment
        card information through the website.
      </p>
      <p>
        The Service applies usage limits (for example, a daily limit on AI
        processing per user and request rate limits) to protect the platform and
        control cost. Limits may be described in your Order Form and may be
        adjusted on notice.
      </p>
      <h2 id="8-customer-content-and-intellectual-property">
        8. Customer Content and intellectual property
      </h2>
      <ul>
        <li>
          <strong>Customer owns Customer Content.</strong> As between the
          parties, Customer owns all Customer Content, including the uploaded
          documents and the output the Service generates for Customer (letters,
          risk reports, corrected claims, extracted data). To the extent
          Heimdall acquires any right in such output, Heimdall assigns it to
          Customer upon creation, subject to Heimdall&apos;s rights in the
          Service itself.
        </li>
        <li>
          <strong>License to Heimdall.</strong> Customer grants Heimdall a
          non-exclusive, worldwide, royalty-free license to host, copy, process,
          transmit, display and otherwise use Customer Content solely to
          provide, secure, support and improve the Service for Customer, as
          permitted by the BAA and the Privacy Policy, and as required by law.
        </li>
        <li>
          <strong>De-identified data.</strong> Where Customer&apos;s BAA permits
          it, Heimdall may create de-identified data from Customer Content in
          accordance with 45 CFR 164.514(b)(2) and the process described in our
          Privacy Policy. De-identified data is not PHI and not Customer
          Content, and Heimdall may use it during and after the term to evaluate
          and improve the Service.
        </li>
        <li>
          <strong>Usage data.</strong> Heimdall may collect and use technical
          and operational data about the use and performance of the Service
          (such as processing times, error rates, token counts and feature
          usage) that does not include PHI or identify any individual, for
          operating and improving the Service.
        </li>
        <li>
          <strong>Heimdall owns the Service.</strong> The Service, including its
          software, user interface, design, prompts, models, templates,
          documentation, trademarks and all improvements, is owned by Heimdall
          and its licensors and is protected by intellectual-property laws.
          Except for the limited right to use the Service under these Terms, no
          rights are granted to you. &quot;Heimdall&quot;, &quot;Heimdall
          Claims&quot; and the Heimdall logo are trademarks or trade names of
          Heimdall Claims, Inc.
        </li>
        <li>
          <strong>Feedback.</strong> If you give us suggestions or feedback, you
          grant us a perpetual, irrevocable, royalty-free license to use it
          without obligation to you. We will never need to use PHI to act on
          feedback, and you should not include PHI in it.
        </li>
        <li>
          <strong>Third-party materials.</strong> The Service uses open-source
          software and public reference data under their respective licenses,
          and refers to code sets owned by others (Section 4). Nothing in these
          Terms grants you rights in third-party materials.
        </li>
      </ul>
      <h2 id="9-confidentiality">9. Confidentiality</h2>
      <p>
        Each party will protect the other party&apos;s Confidential Information
        with at least reasonable care, use it only to perform under these Terms,
        and disclose it only to employees, contractors and advisers who need to
        know it and are bound by confidentiality obligations at least as
        protective. &quot;Confidential Information&quot; means non-public
        information disclosed by one party to the other that is marked
        confidential or that a reasonable person would understand to be
        confidential, including Customer Content, the terms of any Order Form,
        and the non-public features, prompts and security details of the
        Service. It excludes information that is public through no fault of the
        recipient, already known to the recipient, independently developed, or
        rightfully received from a third party. A party may disclose
        Confidential Information when required by law, after giving reasonable
        notice where lawful. PHI is additionally and primarily governed by the
        BAA. These obligations continue for five years after termination, and
        indefinitely for PHI and trade secrets.
      </p>
      <h2 id="10-data-protection-security-and-privacy">
        10. Data protection, security and privacy
      </h2>
      <ul>
        <li>
          <strong>Privacy Policy.</strong> Our{" "}
          <Link href="/privacy">Privacy Policy</Link> describes what information
          we collect, how we use it, how long we keep it, and the rights
          available to you. It is part of these Terms.
        </li>
        <li>
          <strong>BAA.</strong> Our handling of PHI is governed by the BAA,
          which addresses permitted uses and disclosures, safeguards,
          subcontractors, breach notification, access and amendment requests,
          accounting of disclosures, and return or destruction of PHI at
          termination. Customer is the covered entity and remains responsible
          for its own HIPAA obligations, including its notice of privacy
          practices and responses to patient requests, which we will support as
          the BAA requires.
        </li>
        <li>
          <strong>Security.</strong> We maintain administrative, technical and
          physical safeguards appropriate to PHI, summarized in the Privacy
          Policy, and we will not materially decrease the overall security of
          the Service during a subscription term. Customer acknowledges that
          security is a shared responsibility and that Customer is responsible
          for its credentials, devices and users.
        </li>
        <li>
          <strong>Subprocessors.</strong> We use the third-party service
          providers listed at <Link href="/subprocessors">/subprocessors</Link>.
          We will update that page when we add or replace a subprocessor that
          handles Customer Content; Customers may ask to be notified of changes
          by email. Any subprocessor that handles PHI is bound by a business
          associate agreement with us.
        </li>
        <li>
          <strong>Incidents.</strong> We will notify Customer of a breach of
          unsecured PHI without unreasonable delay and no later than 60 days
          after discovery, as the BAA requires, and will cooperate in
          Customer&apos;s investigation and notifications.
        </li>
        <li>
          <strong>Return and deletion.</strong> At termination, we will return
          or destroy Customer&apos;s PHI as the BAA provides, including every
          stored version of its uploaded files, and will confirm the destruction
          to Customer in writing. We retain audit logs (which contain no patient
          data) and other records that law requires us to keep.
        </li>
      </ul>
      <h2 id="11-third-party-services">11. Third-party services</h2>
      <p>
        The Service depends on third-party infrastructure and services,
        including Amazon Web Services, Vercel and SMTP2GO, and refers to data
        published by CMS and payers. We are not responsible for the acts or
        omissions of third parties that we do not control, including payers,
        clearinghouses, your email provider, your internet connection, or
        publicly available reference data, except as expressly provided in a BAA
        or Service Agreement.
      </p>
      <h2 id="12-availability-support-changes-and-beta-features">
        12. Availability, support, changes and beta features
      </h2>
      <ul>
        <li>
          <strong>Availability.</strong> We work to keep the Service available
          and will try to schedule maintenance outside normal business hours,
          but we do not promise uninterrupted or error-free operation. Any
          service-level commitments are only those stated in your Service
          Agreement.
        </li>
        <li>
          <strong>Processing may be interrupted.</strong> Case processing runs
          in the background. A deployment, outage or error can interrupt a
          running case; the Service detects a case that has stopped making
          progress for 15 minutes and lets you retry it. A case that cannot be
          processed is marked as an error with an explanation, never silently
          dropped. Upload limits (currently PDF files only, 25 megabytes and 150
          pages per document) apply and may change.
        </li>
        <li>
          <strong>Support.</strong> We provide support by email during United
          States business hours unless your Service Agreement provides
          otherwise.
        </li>
        <li>
          <strong>Changes.</strong> We may add, change or remove features,
          models, limits or integrations at any time. If a change materially
          reduces the core functionality you pay for, you may terminate the
          affected subscription and receive a pro-rated refund of prepaid,
          unused fees, as your sole remedy.
        </li>
        <li>
          <strong>Beta features.</strong> Features identified as beta, preview,
          pilot or similar are provided for evaluation, may be changed or
          withdrawn at any time, may be less reliable, and are provided without
          any warranty or service commitment, to the maximum extent permitted by
          law.
        </li>
      </ul>
      <h2 id="13-suspension-and-termination">13. Suspension and termination</h2>
      <ul>
        <li>
          <strong>By Customer.</strong> Customer may stop using the Service at
          any time and may terminate as its Service Agreement provides. Visitors
          and Authorized Users may stop using the Service at any time;
          Authorized Users may request deactivation of their account.
        </li>
        <li>
          <strong>By Heimdall.</strong> We may suspend or terminate access to
          the Service, in whole or in part, immediately if: you materially
          breach these Terms, the BAA or the Service Agreement; your use poses a
          security, legal or operational risk to the Service or to others; fees
          are overdue after notice; we are required to do so by law; or we
          discontinue the Service, in which case we will give Customers at least
          60 days&apos; notice where practicable. Where a breach can be cured,
          we will give notice and a reasonable opportunity to cure before
          terminating, unless the breach involves PHI, security or unlawful
          conduct.
        </li>
        <li>
          <strong>Effect.</strong> On termination, your right to use the Service
          ends, and we will handle Customer Content as described in Section 10.
          Customer should download any letters, reports or records it wishes to
          keep before the end of the term. Fees accrued before termination
          remain payable. Sections 1, 3.2, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16, 17
          and 19 survive termination.
        </li>
      </ul>
      <h2 id="14-disclaimers-of-warranties">14. Disclaimers of warranties</h2>
      <p>
        THE SERVICE AND ALL OUTPUT ARE PROVIDED &quot;AS IS&quot; AND &quot;AS
        AVAILABLE&quot;. TO THE MAXIMUM EXTENT PERMITTED BY LAW, HEIMDALL AND
        ITS LICENSORS DISCLAIM ALL WARRANTIES, EXPRESS, IMPLIED OR STATUTORY,
        INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
        PURPOSE, TITLE, NON-INFRINGEMENT, ACCURACY, AND ANY WARRANTIES ARISING
        FROM COURSE OF DEALING OR USAGE OF TRADE.
      </p>
      <p>
        WITHOUT LIMITING THE FOREGOING, HEIMDALL DOES NOT WARRANT THAT: THE
        SERVICE WILL MEET YOUR REQUIREMENTS OR BE UNINTERRUPTED, TIMELY, SECURE
        OR ERROR-FREE; ANY OUTPUT (INCLUDING RISK REPORTS, SUGGESTED EDITS,
        CORRECTED CLAIMS, DENIAL CLASSIFICATIONS, SUCCESS ESTIMATES, DEADLINES
        AND LETTERS) WILL BE ACCURATE, COMPLETE, CURRENT OR SUITABLE FOR
        SUBMISSION; ANY CLAIM WILL BE PAID OR ANY DENIAL OVERTURNED; OR THE
        SERVICE REFLECTS THE RULES OF ANY PARTICULAR PAYER. NO ADVICE OR
        INFORMATION OBTAINED FROM HEIMDALL OR THROUGH THE SERVICE CREATES ANY
        WARRANTY NOT EXPRESSLY STATED IN THESE TERMS. THE SERVICE IS NOT
        MEDICAL, LEGAL, CODING, BILLING OR COMPLIANCE ADVICE, AND HEIMDALL IS
        NOT A FIDUCIARY TO YOU.
      </p>
      <p>
        Some jurisdictions do not allow the exclusion of certain warranties, so
        some of the above exclusions may not apply to you; in that case they
        apply to the maximum extent permitted.
      </p>
      <h2 id="15-limitation-of-liability">15. Limitation of liability</h2>
      <p>
        TO THE MAXIMUM EXTENT PERMITTED BY LAW, IN NO EVENT WILL HEIMDALL, ITS
        AFFILIATES, OFFICERS, DIRECTORS, EMPLOYEES, AGENTS OR LICENSORS BE
        LIABLE FOR: (A) ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL,
        EXEMPLARY OR PUNITIVE DAMAGES; (B) ANY LOSS OF REVENUE, PROFITS,
        BUSINESS, GOODWILL OR DATA; (C) ANY DENIED, REDUCED, DELAYED, RECOUPED
        OR UNRECOVERED CLAIM OR APPEAL AMOUNT, ANY MISSED FILING OR APPEAL
        DEADLINE, ANY PAYER AUDIT, PENALTY OR RECOUPMENT, OR ANY COST OF
        PROCURING SUBSTITUTE SERVICES; OR (D) ANY DAMAGES ARISING FROM YOUR
        RELIANCE ON OUTPUT OF THE SERVICE, IN EACH CASE HOWEVER CAUSED AND UNDER
        ANY THEORY OF LIABILITY, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
        DAMAGES.
      </p>
      <p>
        TO THE MAXIMUM EXTENT PERMITTED BY LAW, HEIMDALL&apos;S TOTAL CUMULATIVE
        LIABILITY ARISING OUT OF OR RELATING TO THE SERVICE OR THESE TERMS WILL
        NOT EXCEED THE GREATER OF (I) THE FEES ACTUALLY PAID BY CUSTOMER TO
        HEIMDALL FOR THE SERVICE IN THE TWELVE MONTHS IMMEDIATELY BEFORE THE
        EVENT GIVING RISE TO THE CLAIM, OR (II) ONE HUNDRED UNITED STATES
        DOLLARS (USD 100).
      </p>
      <p>
        These limitations do not apply to the extent liability cannot be limited
        under applicable law, and do not limit either party&apos;s obligations
        under a BAA to the extent the BAA says otherwise. The parties agree that
        these limitations are an essential basis of the bargain and that the
        Service would not be offered on these commercial terms without them.
      </p>
      <h2 id="16-indemnification">16. Indemnification</h2>
      <ul>
        <li>
          <strong>By Customer.</strong> Customer will defend, indemnify and hold
          harmless Heimdall and its affiliates, officers, directors, employees
          and agents from and against any third-party claim, demand,
          investigation or proceeding, and all resulting losses, damages,
          penalties, fines, costs and expenses (including reasonable
          attorneys&apos; fees), arising out of or relating to: (a) Customer
          Content, including any allegation that it infringes or misappropriates
          a third party&apos;s rights or was uploaded without authority; (b) any
          claim, appeal or other submission Customer makes to a payer or
          government program, including any allegation of false, fraudulent,
          incorrect or non-compliant billing; (c) Customer&apos;s or its
          Authorized Users&apos; violation of these Terms, the BAA or applicable
          law; or (d) Customer&apos;s failure to review output as required by
          Section 4.
        </li>
        <li>
          <strong>By Heimdall.</strong> Heimdall will defend Customer against
          any third-party claim alleging that the Service, as provided by
          Heimdall and used in accordance with these Terms, infringes a United
          States patent, copyright or trademark or misappropriates a trade
          secret, and will pay the damages and costs finally awarded or agreed
          in settlement. This does not apply to claims arising from Customer
          Content, third-party materials, modifications not made by Heimdall,
          combination with items not provided by Heimdall, or use after we have
          offered a non-infringing alternative. If the Service is or may be
          enjoined, Heimdall may procure the right to continue it, modify it to
          be non-infringing, or terminate it and refund prepaid, unused fees.
          This Section states Heimdall&apos;s entire liability for infringement.
        </li>
        <li>
          <strong>Procedure.</strong> The indemnified party must promptly notify
          the indemnifying party of the claim (delay relieves the indemnifying
          party only to the extent it is prejudiced), give the indemnifying
          party sole control of the defense and settlement (except that no
          settlement may impose liability or an admission on the indemnified
          party without its consent), and provide reasonable cooperation at the
          indemnifying party&apos;s expense.
        </li>
      </ul>
      <h2 id="17-governing-law-and-dispute-resolution">
        17. Governing law and dispute resolution
      </h2>
      <ul>
        <li>
          <strong>Governing law.</strong> These Terms and any dispute arising
          out of or relating to them or the Service are governed by the laws of
          the State of Delaware and applicable federal law of the United States,
          without regard to conflict-of-laws rules. The United Nations
          Convention on Contracts for the International Sale of Goods does not
          apply.
        </li>
        <li>
          <strong>Talk to us first.</strong> Before starting any formal
          proceeding, the party raising a dispute will send a written
          description of it to the other party (for Heimdall, at{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>), and the
          parties will try in good faith to resolve it for at least 30 days.
        </li>
        <li>
          <strong>Binding arbitration.</strong> Except as provided below, any
          dispute, claim or controversy arising out of or relating to these
          Terms or the Service that is not resolved informally will be finally
          resolved by binding arbitration administered by the American
          Arbitration Association under its Commercial Arbitration Rules, before
          a single arbitrator, in Wilmington, Delaware, or by video conference
          if the parties agree. The arbitrator will apply these Terms and
          Delaware law, may award any relief a court could award to the
          individual party, and will issue a reasoned written decision. Judgment
          on the award may be entered in any court of competent jurisdiction.
          The Federal Arbitration Act governs the interpretation and enforcement
          of this clause.
        </li>
        <li>
          <strong>Class-action and jury waiver.</strong> TO THE FULLEST EXTENT
          PERMITTED BY LAW, EACH PARTY WAIVES THE RIGHT TO A JURY TRIAL AND TO
          PARTICIPATE IN A CLASS, COLLECTIVE, CONSOLIDATED OR REPRESENTATIVE
          ACTION. Disputes will be arbitrated or litigated only on an individual
          basis.
        </li>
        <li>
          <strong>Exceptions.</strong> Either party may (a) bring an individual
          claim in small-claims court if it qualifies; (b) seek injunctive or
          other equitable relief in court to protect its intellectual property,
          Confidential Information or the security of the Service, or to prevent
          unauthorized use of PHI; and (c) enforce an arbitration award. For
          those matters, and for any matter found not to be arbitrable, the
          parties consent to the exclusive jurisdiction and venue of the state
          and federal courts located in Wilmington, Delaware, and waive any
          objection based on inconvenient forum.
        </li>
        <li>
          <strong>Time limit.</strong> To the extent permitted by law, any claim
          must be brought within one year after it accrues, or it is permanently
          barred.
        </li>
        <li>
          <strong>Government and public entities.</strong> If Customer is a
          government or public entity that is legally prohibited from agreeing
          to arbitration, choice of venue or indemnification, those provisions
          apply to Customer only to the extent permitted by applicable law.
        </li>
      </ul>
      <h2 id="18-changes-to-these-terms">18. Changes to these Terms</h2>
      <p>
        We may revise these Terms from time to time. The &quot;Last
        updated&quot; date at the top shows the current version. For material
        changes, we will give Customers notice through the Service or by email
        to the Customer&apos;s designated contact at least 30 days before they
        take effect, unless the change is required by law or addresses a
        security issue, in which case it may take effect sooner. Continued use
        of the Service after the effective date constitutes acceptance; if you
        do not agree, you must stop using the Service and may terminate as your
        Service Agreement provides. Changes do not apply retroactively to
        disputes that arose before the change.
      </p>
      <h2 id="19-general">19. General</h2>
      <ul>
        <li>
          <strong>Entire agreement.</strong> These Terms, together with the
          Privacy Policy, the Subprocessors page, the BAA and any Service
          Agreement or Order Form, are the entire agreement between you and
          Heimdall about the Service and supersede all prior or contemporaneous
          understandings. In case of conflict, Section 1 governs.
        </li>
        <li>
          <strong>Assignment.</strong> You may not assign or transfer these
          Terms or any rights under them without our prior written consent,
          except to a successor in a merger or sale of substantially all of your
          assets who assumes them in writing and is not a competitor of
          Heimdall. We may assign these Terms to an affiliate or to a successor
          in connection with a merger, acquisition or sale of assets, subject to
          the BAA.
        </li>
        <li>
          <strong>Force majeure.</strong> Neither party is liable for delay or
          failure to perform (other than payment obligations) caused by events
          beyond its reasonable control, including natural disasters, pandemics,
          war, terrorism, labor disputes, governmental action, internet or
          utility failures, or failures of third-party providers, provided it
          uses reasonable efforts to mitigate.
        </li>
        <li>
          <strong>Notices.</strong> Notices to Heimdall must be sent by email to{" "}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and, for legal
          notices, also to our postal address (available on request). Notices to
          Customer may be sent to the email addresses of its administrators or
          posted in the Service. Notices are effective when sent by email, or on
          receipt by mail.
        </li>
        <li>
          <strong>Electronic communications and signatures.</strong> You consent
          to receive communications from us electronically and agree that
          electronic communications satisfy any legal requirement that they be
          in writing. You agree that acceptance by clicking, signing in or using
          the Service has the same legal effect as a signature.
        </li>
        <li>
          <strong>Relationship.</strong> The parties are independent
          contractors. These Terms do not create a partnership, joint venture,
          agency, fiduciary or employment relationship. There are no third-party
          beneficiaries.
        </li>
        <li>
          <strong>Export and sanctions.</strong> You may not use the Service in
          violation of United States export-control or sanctions laws, and you
          represent that you are not located in, or a national of, an embargoed
          country and are not on any United States government restricted-party
          list.
        </li>
        <li>
          <strong>United States government users.</strong> The Service is
          &quot;commercial computer software&quot; and &quot;commercial computer
          software documentation&quot; as those terms are used in the Federal
          Acquisition Regulation, and is licensed to government users only with
          the rights granted to all other users under these Terms.
        </li>
        <li>
          <strong>Severability and waiver.</strong> If any provision is held
          unenforceable, it will be enforced to the maximum extent permissible
          and the remainder will remain in effect, except that if the
          class-action waiver in Section 17 is found unenforceable as to a
          particular claim, the arbitration clause will not apply to that claim.
          A failure to enforce a provision is not a waiver of the right to
          enforce it later.
        </li>
        <li>
          <strong>Interpretation.</strong> Headings are for convenience only.
          &quot;Including&quot; means &quot;including without limitation&quot;.
          No rule of strict construction applies against either party.
        </li>
      </ul>
      <h2 id="20-contact">20. Contact</h2>
      <p>Heimdall Claims, Inc., a Delaware corporation.</p>
      <p>
        Email: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Our
        postal address is available on request by email. Questions about these
        Terms, requests for a Business Associate Agreement or Service Agreement,
        and legal notices should all be sent to that address.
      </p>
    </LegalPage>
  );
}
