// Public-site constants. The contact inbox is the one named in the legal
// documents; the CTAs open the visitor's mail client (no backend for now).
export const CONTACT_EMAIL = "info@heimdallclaims.com";
export const SITE_URL = "https://heimdallclaims.com";
/** Legal entity named in the footer and the legal documents. */
export const COMPANY_LEGAL_NAME = "Heimdall Claims, Inc.";
/** 1200x630 social card: white wordmark on the brand's dark tile. */
export const OG_IMAGE = { url: "/og.png", width: 1200, height: 630 };

function mailto(subject: string, body?: string): string {
  const params = new URLSearchParams({ subject });
  if (body) params.set("body", body);
  return `mailto:${CONTACT_EMAIL}?${params.toString()}`;
}

export const CONTACT_MAILTO = mailto("Heimdall inquiry");
