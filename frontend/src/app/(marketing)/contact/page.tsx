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
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <h1 className="text-3xl font-extrabold tracking-tight">Talk to us</h1>
        <p className="mt-2 text-muted-foreground">
          Questions, a demo, or ready to get started — we&rsquo;ll get back to you fast.
        </p>

        <div className="mt-5">
          <CtaLink href={CONTACT_MAILTO}>Email {CONTACT_EMAIL}</CtaLink>
        </div>

        <div className="mt-6 grid gap-3.5 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-background p-[18px]">
            <div className="font-bold">Request a free demo</div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              See it on your denials. No commitment.
            </p>
            <CtaLink href={DEMO_MAILTO} size="sm" className="mt-3.5 w-full">
              Request demo
            </CtaLink>
          </div>
          <div className="rounded-lg border border-border bg-background p-[18px]">
            <div className="font-bold">Get started</div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Ready for the full product? We&rsquo;ll set you up.
            </p>
            <CtaLink href={GET_STARTED_MAILTO} variant="secondary" size="sm" className="mt-3.5 w-full">
              Get started
            </CtaLink>
          </div>
        </div>
      </div>
    </section>
  );
}
