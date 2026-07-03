import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { CONTACT_EMAIL, CONTACT_MAILTO, GET_STARTED_MAILTO } from "@/lib/site";

export const metadata: Metadata = {
  title: "Contact — Heimdall",
  description: "Get in touch with the Heimdall team about getting started.",
};

export default function ContactPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <h1 className="text-3xl font-extrabold tracking-tight">Talk to us</h1>
        <p className="mt-2 text-muted-foreground">
          Questions or ready to get started — we&rsquo;ll get back to you fast.
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <CtaLink href={CONTACT_MAILTO}>Email {CONTACT_EMAIL}</CtaLink>
          <CtaLink href={GET_STARTED_MAILTO} variant="secondary">
            Get started
          </CtaLink>
        </div>
      </div>
    </section>
  );
}
