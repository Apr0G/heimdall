# Terms of Service

Effective: October 19, 2026. Last updated: October 19, 2026.

These Terms of Service (the "Terms") are a legal agreement between Heimdall Claims, Inc., a Delaware corporation ("Heimdall", "we", "us", "our"), and you. They govern your access to and use of the website at heimdallclaims.com, the Heimdall web application and API, and any related content, documentation and services we provide (together, the "Service").

**Please read these Terms carefully. They include a binding arbitration clause and a class-action waiver (Section 17), disclaimers of warranties (Section 14) and limitations of our liability (Section 15). By visiting the website, submitting a form, signing in, or otherwise using the Service, you agree to these Terms. If you are using the Service on behalf of a healthcare practice or other organization, you represent that you have authority to bind that organization, and "you" includes that organization.**

## 1. Parties, agreements and order of precedence

- **"Customer"** means the healthcare practice or other organization that has entered into an agreement with Heimdall to use the Service.
- **"Authorized User"** means an individual whom Heimdall, at a Customer's request, has invited to use the Service under the Customer's account, such as a physician or office manager.
- **"Visitor"** means anyone who browses the public pages of the website without signing in.
- **"Customer Content"** means all documents, data and other material that a Customer or its Authorized Users upload to or enter in the Service, and all output the Service generates from that material for the Customer (extracted data, analyses, risk reports, drafted letters, corrected claim files and outcome records).
- **"Order Form"** and **"Service Agreement"** mean any written agreement (including a quote, order form, subscription agreement or master services agreement) signed or accepted by Customer and Heimdall that describes the Service, fees and other commercial terms.
- **"BAA"** means the Business Associate Agreement between Customer and Heimdall under HIPAA.

The Service is built to process protected health information ("PHI"). **A Customer may not upload any PHI until a BAA is in place between the Customer and Heimdall.** If there is a conflict among the documents that govern your use of the Service, the order of precedence is: (1) the BAA, with respect to PHI; (2) the Service Agreement or Order Form; (3) these Terms; (4) our [Privacy Policy](/privacy) and any other policy referenced here. Terms printed on a Customer purchase order or similar document have no effect.

## 2. Eligibility, accounts and security

- **Who may use the Service.** The Service is intended for healthcare practices located in the United States that bill United States payers, and for their workforce. You must be at least 18 years old. You may use the Service only in connection with claims for services that your practice actually furnished and is authorized to bill.
- **Invitation only.** There is no self-service sign-up. Accounts are created when Heimdall, at the Customer's direction, invites a person by email. Each Authorized User receives a temporary password by email, valid for 7 days (ask us to re-send it if it expires), and must set a new password and enroll an authenticator app for multi-factor authentication on first sign-in. Multi-factor authentication is mandatory and cannot be disabled.
- **Your credentials are yours alone.** Do not share your account, password or authenticator with anyone, and do not use anyone else's. Each person who uses the Service must have their own account, so that the audit trail HIPAA requires is accurate. You are responsible for everything done under your account until you notify us that it may have been compromised.
- **Sessions.** For security, sessions end after 15 minutes of inactivity and in any event within 60 minutes, after which you must sign in again. Signing out, changing your password, resetting your authenticator or being deactivated ends every session of your account.
- **Roles and the Customer's control.** Accounts belong to the Customer, not to the individual. Heimdall, at the Customer's direction, invites, deactivates and reactivates Authorized Users and decides deactivation requests; Authorized Users may request their own deactivation from the Settings page. Customer is responsible for keeping its roster of Authorized Users current, including telling us promptly to deactivate anyone who leaves the practice. Heimdall's staff hold administrator accounts with a cross-practice view of account records and usage aggregates, as described in the Privacy Policy; that view does not open a Customer's cases and is audit-logged.
- **Lost authenticator and forgotten password.** We provide self-service recovery flows that send one-time codes to the email address on your account. A code expires after 10 minutes and is invalidated after 5 wrong attempts. These are the most sensitive part of the Service; keep control of your work email, and tell us immediately if you receive a code you did not request.
- **Notify us of problems.** Tell us promptly at [info@heimdallclaims.com](mailto:info@heimdallclaims.com) if you suspect unauthorized access to your account or to the Service, or if you notice an error in how the Service handled a case.

## 3. What the Service does, and what it does not do

### 3.1 Features

- **Pre-check.** You upload a draft claim and the supporting clinical notes before the claim is sent to a payer. The Service runs the claim's codes through the Centers for Medicare and Medicaid Services ("CMS") National Correct Coding Initiative ("NCCI") procedure-to-procedure bundling edits and Medically Unlikely Edits, and an AI model compares the clinical documentation to the billed codes. The result is a denial-risk report that lists findings, the denial each finding predicts, and suggested fixes.
- **Corrected claim.** For a draft claim that was produced digitally (not scanned), you may select some or all of the suggested edits and the Service will produce a corrected copy of the claim PDF with those edits applied in place. No AI model is involved in this step; the change is purely mechanical, and the Service re-reads the result to verify it. For a fillable claim form, the Service edits the form fields. For scanned claims you receive the list of edits only.
- **Appeals.** After a denial, you upload the denial or explanation of benefits, the claim and the clinical notes. The Service extracts the structured data, classifies the denial, states whether it appears appealable and why, estimates the likelihood of a successful appeal, recommends an appeal level, and drafts an appeal letter that you can review, download as a PDF, and send. If the analysis indicates that additional records (for example a prior authorization) would strengthen the appeal, you may upload them and the Service will draft a new version of the letter.
- **Outcomes and dashboard.** After you submit an appeal you mark it as submitted and later record the payer's decision and any amount recovered. The dashboard shows win rates and recovered amounts computed from the outcomes your practice reported, and reminds you about appeals whose outcome has not been recorded.

### 3.2 Limits of the Service

Heimdall is a drafting, screening and estimation tool. It is important that you understand what it is not:

- **Heimdall does not submit anything.** It does not transmit claims or appeals to payers, does not connect to clearinghouses, electronic health record systems or payer portals, and has no relationship with any payer. You submit claims and appeals yourself, through your own channels, after your own review.
- **Heimdall is not a medical, legal, coding, billing or compliance advisor**, and it is not a billing company, a clearinghouse, a health plan, a utilization review agent or a medical device. Nothing produced by the Service is medical advice, legal advice, coding advice or a determination of coverage or medical necessity. Every clinical, coding, financial and submission decision remains with the Customer and its licensed and qualified personnel.
- **Heimdall does not guarantee any outcome.** A claim that passes a pre-check may be denied; a flagged claim may be paid; an appeal estimated as likely to succeed may be upheld; and a drafted letter may be rejected. Payers apply their own rules, which change and which the Service may not know.
- **The pre-check baseline is Medicare.** The deterministic edits are the CMS NCCI practitioner edits, refreshed monthly from the quarterly tables CMS publishes; each report records which edition was applied. A payer may be using a different edition, apply additional or different edits, or follow its own policies. The AI documentation review is an opinion generated by a model, not a coding determination.
- **Deadline information is an estimate.** Appeal deadlines shown by the Service are calculated from typical rules for the type of plan detected (currently 120 days from the denial date for Medicare and 60 days otherwise), and the detected plan type may itself be wrong. Your contract with the payer, the denial notice and applicable law control. Verify every deadline yourself.
- **Statistics describe your own reported data.** Win rates and recovered amounts reflect only what your practice entered.

## 4. Artificial intelligence: disclosure and your obligations

The Service uses artificial intelligence. This section explains how, and what we need from you.

- **What runs.** Document text is processed by a large language model (currently Anthropic's Claude, operated through Amazon Bedrock inside our AWS environment) to extract data, classify denials, estimate success, review documentation against codes and draft letters. Scanned documents are read with Amazon Textract. The NCCI bundling and unit checks and the corrected-claim editing are ordinary deterministic software, not AI. Models are called only from our servers, never from your browser, and every model call is recorded with the model and prompt version used. We may change or upgrade the models, prompts and vendors we use.
- **AI output can be wrong.** Language models can misread documents, miss information, state things that are not supported by the documents, apply rules incorrectly, and produce confident-sounding errors. Estimates of appeal success are probabilistic, not predictions, and are not based on your payer's actual decision data. Output quality depends on the legibility and completeness of what you upload; when a document is long, the Service may truncate part of it before analysis, and we record that internally for every model call.
- **A qualified person must review everything before use.** You agree that no risk report, suggested edit, corrected claim, analysis, estimate or letter produced by the Service will be relied on, submitted to a payer or otherwise acted on until it has been reviewed and approved by a person with the training and authority to make that decision for your practice. Drafted letters in particular must be read in full, corrected where necessary, and signed by an authorized representative of the practice before being sent.
- **No emergency or clinical use.** The Service is not designed for, and must not be used for, decisions about patient care, emergencies, or any purpose other than administrative review of claims.
- **No payer or adverse-determination use.** You may not use the Service to make or support a coverage decision, utilization review, or any adverse benefit determination against a patient or provider.
- **Reference data notices.** The Service refers to procedure codes contained in your own documents and in the CMS NCCI tables. CPT is a registered trademark of the American Medical Association. The Service does not provide, license or display the CPT code set or its descriptors; you are responsible for holding any licenses your own use of the CPT code set requires. NCCI edit tables and Claim Adjustment Reason Code descriptions are public reference data and are provided as-is.

## 5. Customer responsibilities

In addition to Section 4, Customer agrees that it will:

- **Have the right to upload what it uploads.** Customer will upload only documents relating to patients the practice has treated and claims the practice is authorized to bill, and only after a BAA is in place. Customer is responsible for having all patient authorizations, notices and consents that its own use of the Service requires and for complying with HIPAA's minimum-necessary standard.
- **Keep uploads accurate and lawful.** Documents must be genuine, unaltered records of services actually furnished and documented. Customer will not upload content that is false, misleading, fraudulent or that it has no right to use, and will not upload files containing malware or anything designed to interfere with the Service.
- **Own every claim and appeal it submits.** A corrected claim produced by the Service reflects edits that Customer selected. Customer is solely responsible for ensuring that any claim or appeal it submits to a payer is accurate, complete, supported by the medical record and compliant with federal and state law, payer contracts and coding rules, including the False Claims Act and anti-kickback and billing-integrity laws. Heimdall does not and cannot verify that a code or modifier is supported by the documentation.
- **Review, decide and keep records.** Customer will review all output as described in Section 4, make its own decisions about what to submit, and keep its own copies of claims, appeals and supporting records as its record-retention duties require. The Service is not a system of record or a backup.
- **Report outcomes truthfully and keep its roster current.** Outcome data you enter should be accurate. Promptly deactivate Authorized Users who no longer need access.
- **Protect its own environment.** Customer is responsible for the security of its devices, networks, email accounts and browsers, and for compliance with its own policies when using the Service from any location.
- **Comply with law.** Customer will use the Service in compliance with all applicable laws and regulations, including HIPAA, state privacy and health-information laws, and the rules of the payers it bills.

## 6. Acceptable use

You will not, and will not permit anyone to:

- access or use the Service without a valid account, share credentials, or attempt to bypass authentication, multi-factor authentication, session limits, rate limits or any other security control;
- access, attempt to access, or probe for another practice's data, or test the Service's security without our prior written permission;
- upload or transmit viruses, malicious code, or anything designed to disrupt, overload or damage the Service or its infrastructure;
- use automated means (bots, scrapers, scripts) to access the Service or to extract data from it, other than through functionality we provide;
- copy, modify, translate, create derivative works of, reverse engineer, decompile or disassemble the Service, or attempt to discover its source code, prompts, models or underlying algorithms, except to the extent applicable law prohibits this restriction;
- rent, lease, sell, sublicense, resell, time-share or otherwise make the Service available to any third party, or use it to build a competing product or to train a competing model;
- use the Service for any purpose other than the administrative review of your own practice's claims, including for any unlawful, fraudulent, deceptive or abusive purpose, or in violation of any payer contract;
- upload PHI of individuals you have no treatment or billing relationship with, or upload any content for which you lack authority;
- remove or alter any proprietary notice in the Service or in its output; or
- interfere with any other user's use of the Service.

We may investigate suspected violations and may suspend or terminate access, remove content, and involve law enforcement where appropriate.

## 7. Fees and payment

Browsing the website costs nothing. Use of the Service by a Customer is subject to the fees set out in the Customer's Order Form or Service Agreement, which may include subscription fees, usage-based fees or both. Unless that agreement says otherwise: fees are stated and payable in United States dollars; invoices are due within 30 days of the invoice date; amounts not paid when due may accrue interest at the lesser of 1.5 percent per month or the maximum rate permitted by law, and we may suspend the Service after notice; fees are exclusive of taxes, and Customer is responsible for all sales, use and similar taxes other than taxes on our income; and fees are non-refundable except as expressly stated in the agreement or required by law. We do not collect payment card information through the website.

The Service applies usage limits (for example, a daily limit on AI processing per user and request rate limits) to protect the platform and control cost. Limits may be described in your Order Form and may be adjusted on notice.

## 8. Customer Content and intellectual property

- **Customer owns Customer Content.** As between the parties, Customer owns all Customer Content, including the uploaded documents and the output the Service generates for Customer (letters, risk reports, corrected claims, extracted data). To the extent Heimdall acquires any right in such output, Heimdall assigns it to Customer upon creation, subject to Heimdall's rights in the Service itself.
- **License to Heimdall.** Customer grants Heimdall a non-exclusive, worldwide, royalty-free license to host, copy, process, transmit, display and otherwise use Customer Content solely to provide, secure, support and improve the Service for Customer, as permitted by the BAA and the Privacy Policy, and as required by law.
- **De-identified data.** Where Customer's BAA permits it, Heimdall may create de-identified data from Customer Content in accordance with 45 CFR 164.514(b)(2) and the process described in our Privacy Policy. De-identified data is not PHI and not Customer Content, and Heimdall may use it during and after the term to evaluate and improve the Service.
- **Usage data.** Heimdall may collect and use technical and operational data about the use and performance of the Service (such as processing times, error rates, token counts and feature usage) that does not include PHI or identify any individual, for operating and improving the Service.
- **Heimdall owns the Service.** The Service, including its software, user interface, design, prompts, models, templates, documentation, trademarks and all improvements, is owned by Heimdall and its licensors and is protected by intellectual-property laws. Except for the limited right to use the Service under these Terms, no rights are granted to you. "Heimdall", "Heimdall Claims" and the Heimdall logo are trademarks or trade names of Heimdall Claims, Inc.
- **Feedback.** If you give us suggestions or feedback, you grant us a perpetual, irrevocable, royalty-free license to use it without obligation to you. We will never need to use PHI to act on feedback, and you should not include PHI in it.
- **Third-party materials.** The Service uses open-source software and public reference data under their respective licenses, and refers to code sets owned by others (Section 4). Nothing in these Terms grants you rights in third-party materials.

## 9. Confidentiality

Each party will protect the other party's Confidential Information with at least reasonable care, use it only to perform under these Terms, and disclose it only to employees, contractors and advisers who need to know it and are bound by confidentiality obligations at least as protective. "Confidential Information" means non-public information disclosed by one party to the other that is marked confidential or that a reasonable person would understand to be confidential, including Customer Content, the terms of any Order Form, and the non-public features, prompts and security details of the Service. It excludes information that is public through no fault of the recipient, already known to the recipient, independently developed, or rightfully received from a third party. A party may disclose Confidential Information when required by law, after giving reasonable notice where lawful. PHI is additionally and primarily governed by the BAA. These obligations continue for five years after termination, and indefinitely for PHI and trade secrets.

## 10. Data protection, security and privacy

- **Privacy Policy.** Our [Privacy Policy](/privacy) describes what information we collect, how we use it, how long we keep it, and the rights available to you. It is part of these Terms.
- **BAA.** Our handling of PHI is governed by the BAA, which addresses permitted uses and disclosures, safeguards, subcontractors, breach notification, access and amendment requests, accounting of disclosures, and return or destruction of PHI at termination. Customer is the covered entity and remains responsible for its own HIPAA obligations, including its notice of privacy practices and responses to patient requests, which we will support as the BAA requires.
- **Security.** We maintain administrative, technical and physical safeguards appropriate to PHI, summarized in the Privacy Policy, and we will not materially decrease the overall security of the Service during a subscription term. Customer acknowledges that security is a shared responsibility and that Customer is responsible for its credentials, devices and users.
- **Subprocessors.** We use the third-party service providers listed at [/subprocessors](/subprocessors). We will update that page when we add or replace a subprocessor that handles Customer Content; Customers may ask to be notified of changes by email. Any subprocessor that handles PHI is bound by a business associate agreement with us.
- **Incidents.** We will notify Customer of a breach of unsecured PHI without unreasonable delay and no later than 60 days after discovery, as the BAA requires, and will cooperate in Customer's investigation and notifications.
- **Return and deletion.** At termination, we will return or destroy Customer's PHI as the BAA provides, including every stored version of its uploaded files, will record the destruction in our append-only audit log, and will confirm it to Customer in writing. We retain audit logs (which contain no patient data) and other records that law requires us to keep.

## 11. Third-party services

The Service depends on third-party infrastructure and services, including Amazon Web Services, Vercel and SMTP2GO, and refers to data published by CMS and payers. We are not responsible for the acts or omissions of third parties that we do not control, including payers, clearinghouses, your email provider, your internet connection, or publicly available reference data, except as expressly provided in a BAA or Service Agreement.

## 12. Availability, support, changes and beta features

- **Availability.** We work to keep the Service available and will try to schedule maintenance outside normal business hours, but we do not promise uninterrupted or error-free operation. Any service-level commitments are only those stated in your Service Agreement.
- **Processing may be interrupted.** Case processing runs in the background. A deployment, outage or error can interrupt a running case; the Service detects a case that has stopped making progress for 15 minutes and lets you retry it. A case that cannot be processed is marked as an error with an explanation, never silently dropped. Upload limits (currently PDF files only, 25 megabytes and 150 pages per document) apply and may change.
- **Support.** We provide support by email during United States business hours unless your Service Agreement provides otherwise.
- **Changes.** We may add, change or remove features, models, limits or integrations at any time. If a change materially reduces the core functionality you pay for, you may terminate the affected subscription and receive a pro-rated refund of prepaid, unused fees, as your sole remedy.
- **Beta features.** Features identified as beta, preview, pilot or similar are provided for evaluation, may be changed or withdrawn at any time, may be less reliable, and are provided without any warranty or service commitment, to the maximum extent permitted by law.

## 13. Suspension and termination

- **By Customer.** Customer may stop using the Service at any time and may terminate as its Service Agreement provides. Visitors and Authorized Users may stop using the Service at any time; Authorized Users may request deactivation of their account.
- **By Heimdall.** We may suspend or terminate access to the Service, in whole or in part, immediately if: you materially breach these Terms, the BAA or the Service Agreement; your use poses a security, legal or operational risk to the Service or to others; fees are overdue after notice; we are required to do so by law; or we discontinue the Service, in which case we will give Customers at least 60 days' notice where practicable. Where a breach can be cured, we will give notice and a reasonable opportunity to cure before terminating, unless the breach involves PHI, security or unlawful conduct.
- **Effect.** On termination, your right to use the Service ends, and we will handle Customer Content as described in Section 10. Customer should download any letters, reports or records it wishes to keep before the end of the term. Fees accrued before termination remain payable. Sections 1, 3.2, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16, 17 and 19 survive termination.

## 14. Disclaimers of warranties

THE SERVICE AND ALL OUTPUT ARE PROVIDED "AS IS" AND "AS AVAILABLE". TO THE MAXIMUM EXTENT PERMITTED BY LAW, HEIMDALL AND ITS LICENSORS DISCLAIM ALL WARRANTIES, EXPRESS, IMPLIED OR STATUTORY, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, NON-INFRINGEMENT, ACCURACY, AND ANY WARRANTIES ARISING FROM COURSE OF DEALING OR USAGE OF TRADE.

WITHOUT LIMITING THE FOREGOING, HEIMDALL DOES NOT WARRANT THAT: THE SERVICE WILL MEET YOUR REQUIREMENTS OR BE UNINTERRUPTED, TIMELY, SECURE OR ERROR-FREE; ANY OUTPUT (INCLUDING RISK REPORTS, SUGGESTED EDITS, CORRECTED CLAIMS, DENIAL CLASSIFICATIONS, SUCCESS ESTIMATES, DEADLINES AND LETTERS) WILL BE ACCURATE, COMPLETE, CURRENT OR SUITABLE FOR SUBMISSION; ANY CLAIM WILL BE PAID OR ANY DENIAL OVERTURNED; OR THE SERVICE REFLECTS THE RULES OF ANY PARTICULAR PAYER. NO ADVICE OR INFORMATION OBTAINED FROM HEIMDALL OR THROUGH THE SERVICE CREATES ANY WARRANTY NOT EXPRESSLY STATED IN THESE TERMS. THE SERVICE IS NOT MEDICAL, LEGAL, CODING, BILLING OR COMPLIANCE ADVICE, AND HEIMDALL IS NOT A FIDUCIARY TO YOU.

Some jurisdictions do not allow the exclusion of certain warranties, so some of the above exclusions may not apply to you; in that case they apply to the maximum extent permitted.

## 15. Limitation of liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, IN NO EVENT WILL HEIMDALL, ITS AFFILIATES, OFFICERS, DIRECTORS, EMPLOYEES, AGENTS OR LICENSORS BE LIABLE FOR: (A) ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY OR PUNITIVE DAMAGES; (B) ANY LOSS OF REVENUE, PROFITS, BUSINESS, GOODWILL OR DATA; (C) ANY DENIED, REDUCED, DELAYED, RECOUPED OR UNRECOVERED CLAIM OR APPEAL AMOUNT, ANY MISSED FILING OR APPEAL DEADLINE, ANY PAYER AUDIT, PENALTY OR RECOUPMENT, OR ANY COST OF PROCURING SUBSTITUTE SERVICES; OR (D) ANY DAMAGES ARISING FROM YOUR RELIANCE ON OUTPUT OF THE SERVICE, IN EACH CASE HOWEVER CAUSED AND UNDER ANY THEORY OF LIABILITY, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

TO THE MAXIMUM EXTENT PERMITTED BY LAW, HEIMDALL'S TOTAL CUMULATIVE LIABILITY ARISING OUT OF OR RELATING TO THE SERVICE OR THESE TERMS WILL NOT EXCEED THE GREATER OF (I) THE FEES ACTUALLY PAID BY CUSTOMER TO HEIMDALL FOR THE SERVICE IN THE TWELVE MONTHS IMMEDIATELY BEFORE THE EVENT GIVING RISE TO THE CLAIM, OR (II) ONE HUNDRED UNITED STATES DOLLARS (USD 100).

These limitations do not apply to the extent liability cannot be limited under applicable law, and do not limit either party's obligations under a BAA to the extent the BAA says otherwise. The parties agree that these limitations are an essential basis of the bargain and that the Service would not be offered on these commercial terms without them.

## 16. Indemnification

- **By Customer.** Customer will defend, indemnify and hold harmless Heimdall and its affiliates, officers, directors, employees and agents from and against any third-party claim, demand, investigation or proceeding, and all resulting losses, damages, penalties, fines, costs and expenses (including reasonable attorneys' fees), arising out of or relating to: (a) Customer Content, including any allegation that it infringes or misappropriates a third party's rights or was uploaded without authority; (b) any claim, appeal or other submission Customer makes to a payer or government program, including any allegation of false, fraudulent, incorrect or non-compliant billing; (c) Customer's or its Authorized Users' violation of these Terms, the BAA or applicable law; or (d) Customer's failure to review output as required by Section 4.
- **By Heimdall.** Heimdall will defend Customer against any third-party claim alleging that the Service, as provided by Heimdall and used in accordance with these Terms, infringes a United States patent, copyright or trademark or misappropriates a trade secret, and will pay the damages and costs finally awarded or agreed in settlement. This does not apply to claims arising from Customer Content, third-party materials, modifications not made by Heimdall, combination with items not provided by Heimdall, or use after we have offered a non-infringing alternative. If the Service is or may be enjoined, Heimdall may procure the right to continue it, modify it to be non-infringing, or terminate it and refund prepaid, unused fees. This Section states Heimdall's entire liability for infringement.
- **Procedure.** The indemnified party must promptly notify the indemnifying party of the claim (delay relieves the indemnifying party only to the extent it is prejudiced), give the indemnifying party sole control of the defense and settlement (except that no settlement may impose liability or an admission on the indemnified party without its consent), and provide reasonable cooperation at the indemnifying party's expense.

## 17. Governing law and dispute resolution

- **Governing law.** These Terms and any dispute arising out of or relating to them or the Service are governed by the laws of the State of Delaware and applicable federal law of the United States, without regard to conflict-of-laws rules. The United Nations Convention on Contracts for the International Sale of Goods does not apply.
- **Talk to us first.** Before starting any formal proceeding, the party raising a dispute will send a written description of it to the other party (for Heimdall, at [info@heimdallclaims.com](mailto:info@heimdallclaims.com)), and the parties will try in good faith to resolve it for at least 30 days.
- **Binding arbitration.** Except as provided below, any dispute, claim or controversy arising out of or relating to these Terms or the Service that is not resolved informally will be finally resolved by binding arbitration administered by the American Arbitration Association under its Commercial Arbitration Rules, before a single arbitrator, in Wilmington, Delaware, or by video conference if the parties agree. The arbitrator will apply these Terms and Delaware law, may award any relief a court could award to the individual party, and will issue a reasoned written decision. Judgment on the award may be entered in any court of competent jurisdiction. The Federal Arbitration Act governs the interpretation and enforcement of this clause.
- **Class-action and jury waiver.** TO THE FULLEST EXTENT PERMITTED BY LAW, EACH PARTY WAIVES THE RIGHT TO A JURY TRIAL AND TO PARTICIPATE IN A CLASS, COLLECTIVE, CONSOLIDATED OR REPRESENTATIVE ACTION. Disputes will be arbitrated or litigated only on an individual basis.
- **Exceptions.** Either party may (a) bring an individual claim in small-claims court if it qualifies; (b) seek injunctive or other equitable relief in court to protect its intellectual property, Confidential Information or the security of the Service, or to prevent unauthorized use of PHI; and (c) enforce an arbitration award. For those matters, and for any matter found not to be arbitrable, the parties consent to the exclusive jurisdiction and venue of the state and federal courts located in Wilmington, Delaware, and waive any objection based on inconvenient forum.
- **Time limit.** To the extent permitted by law, any claim must be brought within one year after it accrues, or it is permanently barred.
- **Government and public entities.** If Customer is a government or public entity that is legally prohibited from agreeing to arbitration, choice of venue or indemnification, those provisions apply to Customer only to the extent permitted by applicable law.

## 18. Changes to these Terms

We may revise these Terms from time to time. The "Last updated" date at the top shows the current version. For material changes, we will give Customers notice through the Service or by email to the Customer's designated contact at least 30 days before they take effect, unless the change is required by law or addresses a security issue, in which case it may take effect sooner. Continued use of the Service after the effective date constitutes acceptance; if you do not agree, you must stop using the Service and may terminate as your Service Agreement provides. Changes do not apply retroactively to disputes that arose before the change.

## 19. General

- **Entire agreement.** These Terms, together with the Privacy Policy, the Subprocessors page, the BAA and any Service Agreement or Order Form, are the entire agreement between you and Heimdall about the Service and supersede all prior or contemporaneous understandings. In case of conflict, Section 1 governs.
- **Assignment.** You may not assign or transfer these Terms or any rights under them without our prior written consent, except to a successor in a merger or sale of substantially all of your assets who assumes them in writing and is not a competitor of Heimdall. We may assign these Terms to an affiliate or to a successor in connection with a merger, acquisition or sale of assets, subject to the BAA.
- **Force majeure.** Neither party is liable for delay or failure to perform (other than payment obligations) caused by events beyond its reasonable control, including natural disasters, pandemics, war, terrorism, labor disputes, governmental action, internet or utility failures, or failures of third-party providers, provided it uses reasonable efforts to mitigate.
- **Notices.** Notices to Heimdall must be sent by email to [info@heimdallclaims.com](mailto:info@heimdallclaims.com) and, for legal notices, also to our postal address (available on request). Notices to Customer may be sent to the email addresses of its administrators or posted in the Service. Notices are effective when sent by email, or on receipt by mail.
- **Electronic communications and signatures.** You consent to receive communications from us electronically and agree that electronic communications satisfy any legal requirement that they be in writing. You agree that acceptance by clicking, signing in or using the Service has the same legal effect as a signature.
- **Relationship.** The parties are independent contractors. These Terms do not create a partnership, joint venture, agency, fiduciary or employment relationship. There are no third-party beneficiaries.
- **Export and sanctions.** You may not use the Service in violation of United States export-control or sanctions laws, and you represent that you are not located in, or a national of, an embargoed country and are not on any United States government restricted-party list.
- **United States government users.** The Service is "commercial computer software" and "commercial computer software documentation" as those terms are used in the Federal Acquisition Regulation, and is licensed to government users only with the rights granted to all other users under these Terms.
- **Severability and waiver.** If any provision is held unenforceable, it will be enforced to the maximum extent permissible and the remainder will remain in effect, except that if the class-action waiver in Section 17 is found unenforceable as to a particular claim, the arbitration clause will not apply to that claim. A failure to enforce a provision is not a waiver of the right to enforce it later.
- **Interpretation.** Headings are for convenience only. "Including" means "including without limitation". No rule of strict construction applies against either party.

## 20. Contact

Heimdall Claims, Inc., a Delaware corporation.

Email: [info@heimdallclaims.com](mailto:info@heimdallclaims.com). Our postal address is available on request by email. Questions about these Terms, requests for a Business Associate Agreement or Service Agreement, and legal notices should all be sent to that address.