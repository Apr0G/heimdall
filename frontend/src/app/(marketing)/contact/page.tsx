import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { CONTACT_EMAIL, CONTACT_MAILTO } from "@/lib/site";

export const metadata: Metadata = {
  title: "Contact — Heimdall",
  description: "Talk to the Heimdall team about appealing denied claims, or get your practice set up.",
};

export default function ContactPage() {
  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <h1 className="text-3xl font-extrabold tracking-tight">Get in touch</h1>
        <p className="mt-3 leading-relaxed text-muted-foreground">
          Whether you&rsquo;re weighing up Heimdall for your practice, have a question about how a
          particular denial would be handled, or just want to talk through your appeals workflow
          &mdash; we&rsquo;d genuinely like to hear from you, and we reply quickly.
        </p>

        <div className="mt-8 space-y-6">
          <div>
            <div className="text-xs font-bold tracking-wider text-muted-foreground uppercase">
              Email us
            </div>
            <a
              href={CONTACT_MAILTO}
              className="mt-1 inline-block text-lg font-semibold text-foreground hover:underline"
            >
              {CONTACT_EMAIL}
            </a>
          </div>

          <div className="rounded-lg border border-border border-l-[3px] border-l-amber-500 bg-background p-5">
            <div className="font-bold">Interested in joining us?</div>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              Most small practices quietly write off denials they&rsquo;re owed on, simply because
              fighting each one eats staff time. If that sounds familiar, tell us a little about your
              practice and we&rsquo;ll get you set up.
            </p>
            <CtaLink href="/get-started" className="mt-4">
              Get started →
            </CtaLink>
          </div>
        </div>
      </div>
    </section>
  );
}
