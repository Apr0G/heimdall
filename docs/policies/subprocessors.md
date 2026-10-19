# Subprocessors

Effective: October 19, 2026. Last updated: October 19, 2026.

This page lists the third-party service providers ("subprocessors") that Heimdall Claims, Inc. uses to deliver the Service, what each one does, and what information it receives. We publish it so that customer practices and their compliance officers can see the complete data flow. It supplements our [Privacy Policy](/privacy) and [Terms of Service](/terms).

Every subprocessor that handles protected health information ("PHI") has signed a Business Associate Agreement ("BAA") with us. Subprocessors that do not handle PHI are contractually limited to using the data they receive only to provide their service to us.

## Subprocessors that handle PHI

All of the following are services of Amazon Web Services, Inc. ("AWS"), operated in the United States (us-east-1 region) under our AWS Business Associate Agreement. Our AWS account is configured so that these services are used only by our own systems; access by AWS personnel is governed by our AWS Business Associate Agreement.

| AWS service | What it does for Heimdall | Data it handles |
|---|---|---|
| Amazon S3 | Stores uploaded PDF documents, text extracted from them, corrected claim files, the archives of AI model requests and responses (30 days), and de-identified exports | PHI at rest, encrypted with keys we control |
| Amazon RDS (PostgreSQL) | The database holding practices, users, cases, extracted data, analyses, letters, risk reports, outcomes and the append-only audit log | PHI at rest, encrypted; not reachable from the internet |
| Amazon ECS on AWS Fargate | Runs the Heimdall API and the one-off operational tasks (migrations, data disposal, de-identification) | PHI in memory while a case is processed |
| Amazon Textract | Optical character recognition of scanned PDF documents | Scanned document images and the text read from them |
| Amazon Bedrock (Anthropic Claude model) | Extracts structured data, classifies denials, estimates appeal success, reviews documentation against billed codes, drafts appeal letters | Document text and the model's output. AWS states that Bedrock does not use prompts or outputs to train models or share them with model providers |
| Amazon Comprehend Medical | Detects remaining identifiers during the de-identification process (Section 5 of the Privacy Policy) | Heimdall-generated text being de-identified |
| AWS Key Management Service | Holds the encryption keys that protect everything above | Keys only |
| Amazon CloudWatch | Application and infrastructure logs and alarms | Technical logs: request paths, status codes, record identifiers and timings. Document contents and patient data are never written to logs |
| AWS CloudTrail, GuardDuty, WAF, VPC Flow Logs | Account audit trail, threat detection, web application firewall, network logs | Security telemetry including IP addresses and request metadata |
| AWS Secrets Manager | Stores database credentials and other secrets used by the Service | Credentials only |

## Subprocessors that do not handle PHI

| Provider | Location | What it does for Heimdall | Data it handles |
|---|---|---|---|
| Amazon Cognito (AWS) | United States | Identity provider for practice staff: sign-in, passwords, multi-factor authentication | Account holders' email addresses, authentication secrets and sign-in events. No patient data |
| Amazon SES and Amazon SNS (AWS) | United States | Email delivery (SES, as a fallback provider when enabled) and internal notifications (SNS): "get started" requests are forwarded to us; operational alarms | Prospect name, work email and message from the "get started" form; alarm and bounce notifications naming staff email addresses |
| Amazon ElastiCache (AWS) | United States | Rate-limiting counters | IP addresses and account identifiers as counter keys, held for minutes to one day |
| AWS Lambda (AWS) | United States | Sends account invitation and password-reset emails on behalf of Cognito | Staff email address and the one-time temporary password or code |
| Vercel, Inc. | United States | Hosts and serves the Heimdall web front end (the application code and public pages) | Standard web-server request logs: IP address, browser user agent, requested page, timestamp; and the hd_authed and hd_theme cookies (a signed-in flag and your theme choice: no token, no PHI). PHI does not pass through Vercel: case data travels directly between the browser and our AWS API, and the session cookie is scoped to the API host |
| SMTP2GO (SMTP2GO Limited) | United States and New Zealand | Active transactional email provider for account emails to practice staff: invitations with temporary passwords, password-reset codes, authenticator-recovery codes; and the internal deactivation-request notice to Heimdall | Staff email address and the message contents listed. Never patient data, by design and by code-level rule |
| Google LLC (Gmail) | United States | Hosts the Heimdall mailbox that receives the "get started" notification and operational alert and bounce notices | Prospect name, work email and message; staff email addresses named in bounce notices. Never patient data |

## Reference data sources (not subprocessors)

The Service downloads public reference tables published by the Centers for Medicare and Medicaid Services (the NCCI procedure-to-procedure and Medically Unlikely Edit tables). No customer data is sent to CMS.

## Changes to this list

We update this page before we start using a new subprocessor that will handle customer data, or when we replace one. Customers with a BAA may ask to be notified of such changes by email by writing to [hello@heimdallclaims.com](mailto:hello@heimdallclaims.com). If a Customer reasonably objects to a new subprocessor on data-protection grounds and we cannot offer an alternative, the Customer may terminate the affected service and receive a refund of prepaid, unused fees.