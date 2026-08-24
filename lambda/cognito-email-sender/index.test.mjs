/**
 * Template routing + the never-leak rule. Decrypt/KMS/network are exercised in
 * the real environment; what must never regress silently is (a) which trigger
 * gets which email, (b) placeholders actually filled, (c) unknown triggers stay
 * silent. Run with `node --test` (the deploy workflow gates on it).
 */
import test from "node:test";
import assert from "node:assert/strict";

// Import renderEmail without touching the handler's AWS clients at module load:
// index.mjs constructs them at import time, so stub the env first.
process.env.KMS_KEY_ARN =
  "arn:aws:kms:us-east-1:000000000000:key/00000000-0000-0000-0000-000000000000";
process.env.SMTP2GO_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:000000000000:secret:x";
process.env.MAIL_FROM = "Heimdall <no-reply@heimdallclaims.com>";
process.env.MAIL_REPLY_TO = "info@heimdallclaims.com";

const { renderEmail } = await import("./index.mjs");

test("invite carries the login email and the temporary password", () => {
  const email = renderEmail(
    "CustomEmailSender_AdminCreateUser",
    "doctor@example.test",
    "Temp-Pass-123",
  );
  assert.equal(email.subject, "Your Heimdall account");
  assert.match(email.html, /doctor@example\.test/);
  assert.match(email.html, /Temp-Pass-123/);
  assert.match(email.text, /Temp-Pass-123/);
});

test("forgot-password carries the code with the reset copy", () => {
  const email = renderEmail("CustomEmailSender_ForgotPassword", "a@b.test", "123456");
  assert.equal(email.subject, "Your Heimdall password reset code");
  assert.match(email.html, /123456/);
  assert.match(email.text, /your password hasn't changed/);
});

test("verification triggers get the generic code email", () => {
  for (const source of [
    "CustomEmailSender_SignUp",
    "CustomEmailSender_ResendCode",
    "CustomEmailSender_VerifyUserAttribute",
  ]) {
    const email = renderEmail(source, "a@b.test", "654321");
    assert.equal(email.subject, "Your Heimdall verification code");
    assert.match(email.text, /654321/);
  }
});

test("unknown / code-less triggers render nothing", () => {
  assert.equal(renderEmail("CustomEmailSender_AccountTakeOverNotification", "a@b.test", null), null);
  assert.equal(renderEmail("SomethingNew_V9", "a@b.test", "1"), null);
});
