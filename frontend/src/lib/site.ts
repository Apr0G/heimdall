// Public-site constants. The email is a placeholder test address until the real
// inbox exists; the CTAs open the visitor's mail client (no backend for now).
export const CONTACT_EMAIL = "hello@heimdallclaims.com";

function mailto(subject: string, body?: string): string {
  const params = new URLSearchParams({ subject });
  if (body) params.set("body", body);
  return `mailto:${CONTACT_EMAIL}?${params.toString()}`;
}

export const GET_STARTED_MAILTO = mailto(
  "Get started with Heimdall",
  "Hi Heimdall team,\n\nWe'd like to get started with the full product. Our practice:\n\nName:\nPractice:\nPhone:\n",
);

export const CONTACT_MAILTO = mailto("Heimdall inquiry");
