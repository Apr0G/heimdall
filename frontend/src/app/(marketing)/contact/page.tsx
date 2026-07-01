import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { CONTACT_EMAIL, CONTACT_MAILTO, DEMO_MAILTO, GET_STARTED_MAILTO } from "@/lib/site";

export const metadata: Metadata = {
  title: "Contact — Heimdall",
  description: "Get in touch with the Heimdall team about a demo or getting started.",
};

export default function ContactPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">Contact us</h1>
      <p className="mt-3 text-muted-foreground">
        Questions, a demo, or getting started — we&rsquo;d love to hear from you. Email us and
        we&rsquo;ll get back to you within one business day.
      </p>

      <div className="mt-6">
        <CtaLink href={CONTACT_MAILTO} size="lg">
          Email {CONTACT_EMAIL}
        </CtaLink>
      </div>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-t-2 border-t-amber-400 p-5">
          <h2 className="font-medium">Request a free demo</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            See Heimdall on your own denials — no commitment.
          </p>
          <CtaLink href={DEMO_MAILTO} variant="secondary" size="sm" className="mt-4">
            Request a demo
          </CtaLink>
        </div>
        <div className="rounded-xl border border-t-2 border-t-blue-500 p-5">
          <h2 className="font-medium">Get started</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Ready for the full product? Let&rsquo;s set your practice up.
          </p>
          <CtaLink href={GET_STARTED_MAILTO} variant="secondary" size="sm" className="mt-4">
            Get started
          </CtaLink>
        </div>
      </div>
    </section>
  );
}
