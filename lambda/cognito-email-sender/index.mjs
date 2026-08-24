/**
 * Cognito Custom Email Sender — routes ALL user-pool email (invites with
 * temporary passwords, password-reset codes) through SMTP2GO as
 * no-reply@heimdallclaims.com, bypassing SES entirely.
 *
 * Why: SES production access was denied (2026-08-24); the sandbox refuses mail
 * to unverified recipients, and Cognito's only native alternatives are its
 * generic default sender or SES. This trigger is the supported escape hatch:
 * Cognito hands us the secret (temp password / code) encrypted with our KMS
 * key via the AWS Encryption SDK envelope format — plain kms:Decrypt cannot
 * read it, hence the @aws-crypto/client-node dependency.
 *
 * Invariants (mirror backend/app/services/mailer.py):
 *  - These emails carry auth codes to practice staff — NEVER PHI. That rule is
 *    what makes a non-BAA provider acceptable here.
 *  - Never log recipients, codes, subjects, or provider response bodies (they
 *    echo the address). Log triggerSource + outcome only.
 *  - Fail loudly: a throw surfaces as a Cognito error, which beats silently
 *    swallowing an invite. The CloudWatch alarm on Errors pages the operator.
 */

import { buildDecrypt } from "@aws-crypto/decrypt-node";
import { KmsKeyringNode } from "@aws-crypto/kms-keyring-node";
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from "@aws-sdk/client-secrets-manager";

const SMTP2GO_ENDPOINT = "https://api.smtp2go.com/v3/email/send";
const LOGIN_URL = "https://heimdallclaims.com/login";

const { decrypt } = buildDecrypt();
const keyring = new KmsKeyringNode({ keyIds: [process.env.KMS_KEY_ARN] });
const secrets = new SecretsManagerClient({});

let cachedApiKey = null;
async function apiKey() {
  if (!cachedApiKey) {
    const out = await secrets.send(
      new GetSecretValueCommand({ SecretId: process.env.SMTP2GO_SECRET_ARN }),
    );
    cachedApiKey = out.SecretString;
  }
  return cachedApiKey;
}

async function decryptCode(encoded) {
  if (!encoded) return null;
  const { plaintext } = await decrypt(keyring, Buffer.from(encoded, "base64"));
  return plaintext.toString("utf8");
}

// Copy mirrors the Cognito templates in main.tf so switching senders does not
// change what users receive. {####} -> code, {username} -> login email.
export function renderEmail(triggerSource, email, code) {
  const invite = {
    subject: "Your Heimdall account",
    html: `<p>Hello,</p>
<p>An account has been created for you on Heimdall, your practice's appeal-drafting workspace.</p>
<p>Sign in at <a href="${LOGIN_URL}">heimdallclaims.com/login</a> with:</p>
<p>Email: ${email}<br/>Temporary password: <strong>${code}</strong></p>
<p>You'll be asked to choose your own password and set up an authenticator app. This temporary password expires in 7 days — if it has, ask your administrator to send a new one.</p>
<p>— Heimdall</p>`,
    text: `Hello,\n\nAn account has been created for you on Heimdall. Sign in at ${LOGIN_URL} with:\n\nEmail: ${email}\nTemporary password: ${code}\n\nYou'll be asked to choose your own password and set up an authenticator app. This temporary password expires in 7 days.\n\n— Heimdall`,
  };
  const reset = {
    subject: "Your Heimdall password reset code",
    html: `<p>Hello,</p>
<p>Someone asked to reset the password for your Heimdall account. Enter this code on the reset screen:</p>
<p style="font-size:20px;letter-spacing:4px"><strong>${code}</strong></p>
<p>The code expires in one hour. If you didn't request this, you can ignore this email — your password hasn't changed.</p>
<p>— Heimdall</p>`,
    text: `Hello,\n\nSomeone asked to reset the password for your Heimdall account. Enter this code on the reset screen:\n\n${code}\n\nThe code expires in one hour. If you didn't request this, you can ignore this email — your password hasn't changed.\n\n— Heimdall`,
  };
  const verify = {
    subject: "Your Heimdall verification code",
    html: `<p>Hello,</p><p>Your Heimdall verification code is:</p>
<p style="font-size:20px;letter-spacing:4px"><strong>${code}</strong></p>
<p>— Heimdall</p>`,
    text: `Hello,\n\nYour Heimdall verification code is: ${code}\n\n— Heimdall`,
  };

  switch (triggerSource) {
    case "CustomEmailSender_AdminCreateUser":
    case "CustomEmailSender_ResendCode_AdminCreateUser":
      return invite;
    case "CustomEmailSender_ForgotPassword":
      return reset;
    case "CustomEmailSender_SignUp":
    case "CustomEmailSender_ResendCode":
    case "CustomEmailSender_UpdateUserAttribute":
    case "CustomEmailSender_VerifyUserAttribute":
      return verify;
    default:
      // e.g. AccountTakeOverNotification — carries no code; nothing to send.
      return null;
  }
}

export async function handler(event) {
  const triggerSource = event.triggerSource ?? "unknown";
  const email = event.request?.userAttributes?.email;
  if (!email) {
    console.warn(JSON.stringify({ msg: "no email attribute", triggerSource }));
    return;
  }

  const code = await decryptCode(event.request?.code);
  const rendered = renderEmail(triggerSource, email, code);
  if (!rendered || !code) {
    console.log(JSON.stringify({ msg: "no email for trigger", triggerSource }));
    return;
  }

  const response = await fetch(SMTP2GO_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Smtp2go-Api-Key": await apiKey(),
    },
    body: JSON.stringify({
      sender: process.env.MAIL_FROM,
      to: [email],
      subject: rendered.subject,
      text_body: rendered.text,
      html_body: rendered.html,
      custom_headers: [
        { header: "Reply-To", value: process.env.MAIL_REPLY_TO },
      ],
    }),
  });

  let succeeded = 0;
  try {
    succeeded = (await response.json())?.data?.succeeded ?? 0;
  } catch {
    /* BadResponse handled below */
  }
  if (response.status >= 400 || succeeded !== 1) {
    // Status only — the body echoes the recipient address.
    console.error(
      JSON.stringify({ msg: "send failed", triggerSource, status: response.status }),
    );
    throw new Error(`smtp2go send failed (HTTP ${response.status})`);
  }
  console.log(JSON.stringify({ msg: "sent", triggerSource }));
}
