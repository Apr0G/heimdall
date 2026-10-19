# Privacy Policy

Effective: October 19, 2026. Last updated: October 19, 2026.

This Privacy Policy explains how Heimdall Claims, Inc. ("Heimdall", "we", "us", "our"), a Delaware corporation, collects, uses, shares and protects information when you visit heimdallclaims.com, use the Heimdall application and API (together, the "Service"), fill in a form on our site, or communicate with us. It also explains, for transparency, how we handle the health information that healthcare practices entrust to us, even though that information is governed first by law and by our contracts with those practices.

Please read this policy together with our [Terms of Service](/terms) and our [Subprocessors](/subprocessors) list. If you do not agree with this policy, please do not use the Service.

## 1. Who we are and the roles we play

Heimdall is a software company. We provide a web-based tool that helps small United States healthcare practices check draft insurance claims for denial risk before submission, analyze claim denials, and draft appeal letters. We are not a healthcare provider, a health plan, a clearinghouse, a billing company, or a law firm.

We handle information in two different roles, and the rules differ between them:

- **As a business, for our own purposes.** This covers information about visitors to our website, prospective customers who contact us, and the staff of practices who hold user accounts (for example their work email address and login activity). This policy is the main document that governs that information.
- **As a business associate under HIPAA, on behalf of a practice.** When a practice uploads claim documents, denial letters or clinical notes, those documents contain protected health information ("PHI") about the practice's patients. Under the Health Insurance Portability and Accountability Act ("HIPAA"), the practice is the covered entity and Heimdall is its business associate. We process that PHI only as the practice instructs and as permitted by the Business Associate Agreement ("BAA") between the practice and Heimdall. Where this policy and a BAA conflict with respect to PHI, the BAA controls.

**If you are a patient.** Heimdall does not have a direct relationship with patients. Your healthcare provider decides what information to upload and is responsible for your privacy notices and for responding to your requests about your health records. Please direct any request about your health information to your provider. We will help the provider respond, as our BAA requires.

## 2. Information we collect

### 2.1 Information you give us directly

- **"Get started" and contact requests.** If you submit the form at /get-started, we collect your name, your work email address and the free-text description of your practice that you choose to write. If you email us, we collect your email address and whatever you include in the message. We ask you not to include any patient information in these messages.
- **Account information.** Heimdall accounts are created by invitation only. When Heimdall, at a practice's request, invites a member of the practice's staff, we record that person's full name, work email address, role within the practice (doctor or office manager), the practice they belong to, the time of their last sign-in, and the time of their last request (updated roughly once a minute while they use the Service, to enforce the inactivity timeout). Passwords and authenticator secrets are handled by our identity provider (Amazon Cognito). Heimdall never stores your password: when you sign in or change it, the password is passed to Cognito for verification and is not written to any log.
- **Practice information.** For each customer practice we record the practice name, National Provider Identifier (NPI), tax identification number, business address, and the version and date of the BAA the practice signed.
- **Things you type into the Service.** This includes notes you add when logging the outcome of an appeal, the reason you give when requesting that your own account be deactivated, and the edits you select when correcting a draft claim.
- **Support and other communications.** Records of your correspondence with us.

### 2.2 Information collected automatically

When you use the website or the Service, our systems record technical information about the request. This includes:

- **Network and device data.** Your IP address, browser type and version (the "user agent" string), the date and time of the request, the page or API endpoint requested, the response status, and internal request identifiers. We do not collect precise geolocation and we do not fingerprint devices.
- **Account activity (audit logs).** For every login, logout, password change, authenticator reset, and every time an account views a case, downloads a document or letter, uploads a file, or changes account settings, we write an entry to an append-only audit log that records who did what, when, from which IP address and with which browser. These records exist because HIPAA requires us to be able to show who accessed health information. The application cannot edit or delete them (the database permissions forbid it); only the database owner could, and that access is itself logged by AWS. We keep them for at least six years. Audit entries never contain the contents of documents or patient data.
- **Security and rate-limiting data.** Our firewall (AWS WAF), network flow logs and rate limiter use your IP address and, for logged-in users, your account identifier to block abuse and brute-force login attempts. Rate-limit counters live for minutes to at most one day.
- **Cookies and browser storage.** Described in Section 7. We do not use advertising cookies, analytics trackers, pixels or any third-party tracking scripts on our site or in the Service.

### 2.3 Health information uploaded by practices (PHI)

Practices upload PDF documents to the Service: draft or submitted claims (for example a CMS-1500 form), denial letters or explanations of benefits, clinical notes, and sometimes prior-authorization records or prior-treatment records. These documents routinely contain PHI such as patient names, dates of birth, dates of service, diagnosis and procedure codes, insurance member identifiers, claim numbers and clinical narratives.

From these documents the Service produces and stores:

- extracted structured data (payer, plan type, claim number, denial codes, procedure and diagnosis codes, modifiers, dates of service, denial date, billed and denied amounts);
- the patient's initials and a keyed one-way hash of the insurance member identifier (we never store the member identifier itself in readable form);
- the name, size, type and cryptographic hash of each uploaded file as you supplied it (file names you choose may themselves contain patient names, so please name files carefully);
- the text extracted from each document (so that it does not have to be re-read each time);
- for appeals: a denial classification, an estimate of appeal success, the reasoning behind it, the recommended appeal level, any additional records the analysis suggests you obtain, the estimated appeal deadline, and the drafted appeal letter and its PDF;
- for pre-checks: a denial-risk report, proposed edits, and, if the practice chooses, a corrected copy of the claim PDF;
- the outcome the practice reports (whether you appealed; overturned, upheld, partial, withdrawn or pending; amount recovered; resolution date; notes; and who recorded it and when);
- a record of every AI model call made while processing the case (the model used, the prompt version, token counts, timing and success or failure) together with an archive of the exact text sent to and received from the model, kept for 30 days for quality and error investigation.

Section 4 explains how this information is used and protected.

### 2.4 Information we do not collect

We do not collect payment card details through the website or the Service (there is no online checkout). We do not collect Social Security numbers of account holders (a practice's tax identification number may be its owner's Social Security number if the practice is a sole proprietorship). We do not knowingly collect information from children (see Section 11). We do not buy information about you from data brokers.

## 3. How we use information

We use the information described in Section 2 to:

- provide, operate, secure and support the Service, including authenticating you, enforcing multi-factor authentication, signing you out after inactivity, and preventing abuse;
- respond to your "get started" request or other inquiry, set up your practice, and communicate with you about your account, security events and changes to the Service or to our terms;
- send the transactional emails the Service needs: account invitations with a temporary password, one-time codes for password reset and for recovering access when you lose your authenticator app, and an internal notice to Heimdall when a user asks to be deactivated. These emails never contain patient information;
- keep the audit logs that HIPAA requires and investigate security incidents;
- understand how the Service is used, in aggregate, so that we can fix problems and improve it (for example, how long processing takes, how often a step fails, and how much the AI processing costs per practice);
- comply with law, enforce our Terms of Service, and protect the rights, safety and property of Heimdall, our customers and others.

We use PHI only to perform the Service for the practice that uploaded it, to carry out our obligations under the BAA, for our own management and administration and legal responsibilities as HIPAA permits, and, where the practice's BAA allows it, to create de-identified data as described in Section 5. We do not use PHI for marketing, and we do not sell PHI or any other personal information.

## 4. How health information is processed and protected

This section describes the data flow for PHI so that practices and their patients can see exactly what happens.

- **Where it lives.** All PHI is stored in Amazon Web Services ("AWS") data centers in the United States (us-east-1 region): uploaded files, extracted text and model archives in Amazon S3; structured case data in an Amazon RDS PostgreSQL database. Everything is encrypted at rest with AWS Key Management Service keys that we control, and in transit with TLS. The database is not reachable from the public internet.
- **Who processes it.** Scanned PDFs are read with Amazon Textract (optical character recognition). Document text is then sent to a large language model (Anthropic's Claude) running inside Amazon Bedrock, which extracts data, classifies the denial, estimates appeal success, reviews the clinical documentation against the billed codes and drafts letters. These are AWS services covered by our Business Associate Agreement with AWS. AWS states that Amazon Bedrock does not use customer prompts or outputs to train its models and does not share them with model providers. Amazon Comprehend Medical is used only during the de-identification process described in Section 5. The complete list of vendors is on our [Subprocessors](/subprocessors) page.
- **What never happens.** Our web front end, hosted by Vercel, serves only the application code. Documents and case data travel directly between your browser and our AWS infrastructure, and the session cookie that authorizes those requests is scoped to our API, so PHI does not pass through or rest on Vercel's servers. AI models are never called from your browser. Document contents and patient data are never written to application logs; our logging code strips identifiers defensively, and our error reporting withholds any message that could echo document contents.
- **Who can see it.** Only the staff of the practice that uploaded a case can view that case; every database query is scoped to the practice, and we test this. Heimdall's own staff hold administrator accounts that give a cross-practice view of account records (names, work email addresses, roles, status, last activity), pending deactivation requests and per-practice usage aggregates (case counts, billed and denied totals, AI processing cost); that view does not open a practice's cases, and every use of it is audit-logged. Heimdall personnel do not routinely access PHI. When access is necessary (for example, to investigate a processing failure at a practice's request) it is limited to what is needed and is itself recorded.
- **How it is deleted.** Temporary upload objects are deleted after one day. Model request and response archives are deleted after 30 days. Database backups are kept for 30 days. When a practice ends its relationship with us, we return or destroy its PHI as the BAA requires, including all stored versions of its files, and we confirm the destruction to the practice in writing and keep that confirmation as a compliance record. Audit logs, which contain no patient data, are retained (Section 8).

## 5. De-identified data and improving the Service

With a practice's written permission in its BAA (and only then), we may create de-identified data from completed appeal cases to evaluate and improve the Service, including the AI models and prompts behind it.

Here is what that means in practice:

- **What is included.** Only text that our own system generated (the clinical summary, the appeal analysis and reasoning, and the drafted appeal letter), together with non-identifying structured fields such as payer name, plan type, the practice's state, dollar amounts, procedure and diagnosis codes, the year of service, and the reported outcome. The raw uploaded documents and the text extracted from them are never included.
- **How identifiers are removed.** We follow the HIPAA Safe Harbor standard (45 CFR 164.514(b)(2)). Every free-text field passes through three independent layers: a rule set written for this purpose, an open-source clinical de-identification model, and Amazon Comprehend Medical's PHI detection. Anything any layer finds is removed. A separate, broader scan then checks the result; if it finds anything that looks like an identifier, the export is aborted. Nothing in a de-identified record is derived from an identifier: each record gets a new random code, and the only link between that code and a patient is a table that never leaves our database. Dates are reduced to the year, ages over 89 are generalized, and initials, names, addresses, employer references and identification numbers are removed.
- **Human review before use.** Even after all of that, the output is treated as PHI and held in a quarantine area for up to 30 days until a named reviewer has read it, checked it against the Safe Harbor "no actual knowledge" standard, and recorded their attestation and the file's cryptographic hash in an append-only release log. A corpus that is not reviewed and released simply expires.
- **How we use and keep it.** Released de-identified data is no longer PHI under HIPAA and may be retained indefinitely and used to measure, test and improve the Service. We do not sell de-identified data. If we ever share it with a research or technology partner, the recipient will be contractually prohibited from attempting to re-identify anyone.
- **Opting out.** A practice whose BAA does not permit de-identification is never included. A practice that is included may withdraw permission for future exports by amending its BAA; data already released cannot be recalled because it no longer identifies anyone.

## 6. How we share information

We share personal information only in the following circumstances:

- **Service providers (subprocessors).** Companies that host and operate the Service on our behalf: AWS (infrastructure, storage, databases, OCR, AI processing, identity, email, monitoring), Vercel (hosting of the web front end) and SMTP2GO (delivery of account emails to practice staff). Each is bound by contract to use the information only to provide its service to us. The current list, with what each one receives, is at [/subprocessors](/subprocessors). PHI goes only to subprocessors that have signed a Business Associate Agreement with us.
- **Within your practice.** Because all case data belongs to the practice, every authorized user of your practice can see the practice's cases. Heimdall's administrators see account records and usage aggregates across practices as described in Section 4.
- **Our own mailbox provider.** The notification we receive when you submit the "get started" form, and operational alerts about the Service (which can name a staff email address when an account email bounces), are delivered to a Heimdall mailbox hosted by Google (Gmail). No patient data is ever sent there.
- **Legal requirements.** When we believe in good faith that disclosure is required by law, regulation, legal process or a governmental request, or is necessary to protect the rights, property or safety of Heimdall, our customers or the public. Where PHI is involved we will follow the BAA and HIPAA, which generally require that we notify the practice unless the law prohibits it.
- **Business transfers.** If Heimdall is involved in a merger, acquisition, financing, reorganization or sale of assets, information may be transferred as part of that transaction. Any successor will be bound by this policy and, for PHI, by the applicable BAAs.
- **Professional advisers.** Our lawyers, accountants, auditors and insurers, under confidentiality obligations.
- **With your direction or consent.**

We do not sell personal information, we do not share it for cross-context behavioral advertising, and we do not allow third parties to collect information about you on our site for their own purposes.

## 7. Cookies and browser storage

We use a small number of first-party cookies that are necessary for the Service to work. We do not use third-party cookies, advertising cookies or analytics cookies.

| Name | Set by | Purpose | Readable by scripts | Lifetime |
|---|---|---|---|---|
| hd_session | Our API (api.heimdallclaims.com) | Holds your signed session token after you sign in. Marked HttpOnly, Secure and SameSite=Lax so that scripts cannot read it and it is only sent to our API. | No | At most 60 minutes, and ended earlier after 15 minutes of inactivity or when you sign out. |
| hd_authed | Our web app | A flag with the single value "1" that tells the web app you are signed in, so it can send you to the right page. Contains no token and no personal data. Sent to Vercel, which serves the web app. | Yes | Up to 60 minutes; cleared when you sign out. |
| hd_theme | Our web app | Remembers whether you chose the light or dark theme so the correct icon and colors load. Sent to Vercel, which serves the web app. | Yes | One year. |

The web app also stores your theme preference in your browser's local storage. Fonts and all scripts are served from our own domain; no request is made to a font or script provider when you load a page.

You can delete or block cookies in your browser settings. If you block the hd_session cookie you will not be able to sign in. Because we do not track visitors, we do not respond differently to "Do Not Track" or Global Privacy Control signals; there is no tracking to turn off.

## 8. How long we keep information

| Information | Retention |
|---|---|
| "Get started" and contact inquiries | For as long as needed to respond and follow up, and then deleted on request or when no longer needed. |
| Account information (name, work email, role) | For the life of the account, and afterwards as long as audit log entries reference the account (at least six years), because deleting the account record would break the integrity of the audit trail. The account is deactivated and can no longer sign in. |
| Practice information | For the life of the customer relationship and for six years afterwards for compliance records. |
| Uploaded documents, extracted text, case data, letters, risk reports, corrected claims | For the life of the customer relationship, or sooner on the practice's written request to us (there is no self-service delete in the Service). Returned or destroyed at termination as the BAA requires. |
| Temporary upload objects | One day. |
| Archives of AI model requests and responses | 30 days. |
| Database backups | 30 days (rolling). |
| Audit logs (who accessed what, when, from where) | At least six years; append-only. |
| Application and server logs (no document contents) | 30 to 90 days depending on the component. Network flow logs: 90 days. AWS account activity logs (CloudTrail): seven years in write-protected storage, plus a one-year searchable copy. |
| De-identified quarantine exports | 30 days unless reviewed and released. |
| Released de-identified data | Indefinitely (it is no longer PHI). |
| Email delivery records held by our email providers | Per each provider's standard retention for delivery metadata. |

## 9. Security

We built the Service for health information from the start. Current safeguards include: encryption of all data at rest with customer-managed keys and in transit with TLS; a private database with no public network access; mandatory multi-factor authentication (an authenticator app) and strong password rules for every account; automatic sign-out after 15 minutes of inactivity; server-side revocation of sessions on logout, password change or account deactivation; role-based access controls; append-only audit logs of every access to health information; practice-level isolation enforced on every database query and verified by automated tests; a web application firewall and rate limiting; a strict Content Security Policy that prevents scripts from third-party origins and limits where your browser may send data; secrets kept in a managed secrets store rather than in code; automated dependency, secret and static-analysis scanning on every code change; and security monitoring and alerting across our AWS account.

No system can be guaranteed to be perfectly secure. If we discover a breach of unsecured PHI we will notify the affected practice without unreasonable delay and in any case within 60 days of discovery, as HIPAA and our BAA require, with the information the practice needs to meet its own notification duties. If a security incident affects personal information for which we are responsible directly (for example, contact details of a prospective customer), we will notify affected individuals and regulators as applicable law requires.

If you believe you have found a security vulnerability in the Service, please email us at [info@heimdallclaims.com](mailto:info@heimdallclaims.com) with enough detail for us to reproduce it. We ask that you do not access or modify data that is not yours and that you give us a reasonable time to fix the issue before disclosing it publicly.

## 10. Your choices and rights

### 10.1 Account holders

Your account belongs to your practice. You can change your password at any time from the Settings page, and you can reset your authenticator there (we email you a code, sign you out everywhere, and you enroll a new authenticator at your next sign-in). To correct your name or role, or to have your account deactivated, your practice emails us and we make the change; you can also file a deactivation request yourself from the Settings page, which Heimdall reviews with your practice. Deactivation stops all access immediately. For the reasons in Section 8, the account record and audit entries are retained after deactivation.

### 10.2 Prospective customers and website visitors

If you have contacted us and would like us to delete your contact details or stop contacting you, email us at [info@heimdallclaims.com](mailto:info@heimdallclaims.com) and we will do so unless we need the information for a legitimate business or legal reason, which we will explain.

### 10.3 Patients

Please contact your healthcare provider. Requests to access, correct, restrict or obtain an accounting of disclosures of your health records are handled by the provider under HIPAA, and we support the provider in fulfilling them.

### 10.4 Rights under United States state privacy laws

Depending on where you live, state privacy laws (for example in California, Colorado, Connecticut, Virginia, Texas, Oregon and others) may give you rights to know what personal information we hold about you, to access it in a portable format, to correct it, to delete it, to opt out of its sale, sharing for targeted advertising, or use in profiling that produces legal or similarly significant effects, and not to be discriminated against for exercising those rights. Many of those laws do not apply to PHI governed by HIPAA, to information about employees and business contacts, or to businesses of our size; but we will honor these requests from any United States resident regardless of whether the law technically requires it.

To exercise a right, email [info@heimdallclaims.com](mailto:info@heimdallclaims.com). We will need to verify that you are the person the information is about (usually by confirming control of the email address on record). You may use an authorized agent; we will ask for proof of the agent's authority. We will respond within 45 days, or tell you if we need more time. If we decline a request we will tell you why, and you may appeal by replying to our response.

For the avoidance of doubt: we do not sell personal information; we do not share it for cross-context behavioral advertising; we do not use it for automated decisions that produce legal or similarly significant effects about individuals; and we do not collect personal information from consumers for those purposes. The categories of personal information we collect, the sources, the purposes and the categories of recipients are described in Sections 2, 3 and 6 of this policy, which also serves as our notice at collection.

## 11. Children

The website and the Service are intended for healthcare professionals and are not directed to children. We do not knowingly collect personal information directly from anyone under 18. Documents uploaded by a practice may relate to pediatric patients; that information is PHI handled on the practice's behalf as described in Section 4. If you believe a child has provided us personal information directly, contact us and we will delete it.

## 12. Where information is processed; users outside the United States

Heimdall operates in the United States and stores and processes information in the United States. The Service is designed for United States healthcare practices and United States insurance claims. If you access the website from outside the United States, you understand that your information will be transferred to and processed in the United States, where privacy laws may differ from those of your country.

## 13. Communications from us

We send the emails needed to run your account (invitations, one-time codes, and any security notice we may need to send) and we reply to the inquiries you send us. We do not send marketing newsletters. If we ever introduce marketing email, we will ask for your consent first and every message will include a way to unsubscribe. Account and security emails cannot be opted out of while your account is active, because they are how the Service works.

## 14. Links and third-party sites

Our site and the Service may link to third-party resources, for example payer websites, CMS reference pages or regulatory texts. Those sites have their own privacy practices and we are not responsible for them.

## 15. Changes to this policy

We will update this policy when our practices change. The "Last updated" date at the top tells you when. For material changes affecting account holders, we will give notice through the Service or by email to the practice's designated contact at least 30 days before the change takes effect, unless a shorter period is required by law. Earlier versions are retained in our records and are available on request.

## 16. Contact us

Heimdall Claims, Inc., a Delaware corporation.

Email: [info@heimdallclaims.com](mailto:info@heimdallclaims.com). Our postal address is available on request by email.

Privacy inquiries, requests under Section 10, security reports and HIPAA-related questions should all be sent to that address with a subject line that says what the message is about. If you are a practice with a BAA and need to report a suspected incident, please mark the subject "Security incident" so that it is handled first.