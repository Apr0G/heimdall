import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { HeroPreview } from "@/components/hero-preview";
import { Reveal } from "@/components/reveal";

export const metadata: Metadata = {
  title: "Heimdall — Appeal denied insurance claims",
  description:
    "Heimdall reads your insurance denial, estimates whether it's worth appealing, and drafts a payer-ready appeal letter — so your practice recovers revenue it already earned.",
  openGraph: {
    title: "Heimdall — Appeal denied insurance claims",
    description:
      "Upload the denial, the claim, and your notes. Heimdall analyzes it and drafts the appeal letter.",
    type: "website",
  },
};

const HERO_BG = {
  backgroundImage:
    "radial-gradient(120% 90% at 20% 0%, color-mix(in oklab, var(--color-amber-500) 20%, transparent), transparent 60%), radial-gradient(120% 90% at 90% 20%, color-mix(in oklab, var(--color-blue-500) 18%, transparent), transparent 55%)",
};

const STEPS = [
  {
    title: "Upload",
    body: "Drop in the denial/EOB, the original claim, and clinical notes. PDF only.",
  },
  {
    title: "Review",
    body: "Check the denial breakdown, success estimate, and the drafted appeal letter.",
  },
  {
    title: "Send",
    body: "Download the PDF, submit it yourself, then log the outcome to sharpen future odds.",
  },
];

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden px-4 pt-20 pb-20 text-center sm:pt-28">
        <div
          aria-hidden
          style={HERO_BG}
          className="animate-aurora pointer-events-none absolute inset-0 -z-10"
        />
        <div className="relative mx-auto max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground shadow-sm">
            <span className="size-1.5 rounded-full bg-amber-500" />
            Built for small US practices
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-extrabold tracking-tight text-balance sm:text-[52px] sm:leading-[1.03]">
            Stop writing off <span className="text-amber-600">denied claims.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted-foreground">
            Upload the denial, the claim, and your notes. Heimdall analyzes the denial, estimates
            your odds, and drafts a payer-ready appeal letter — in minutes.
          </p>
          <div className="mt-8 flex justify-center">
            <CtaLink href="/get-started" size="lg">
              Get started
            </CtaLink>
          </div>
        </div>
        <Reveal className="relative">
          <HeroPreview />
        </Reveal>
      </section>

      {/* Problem / Solution */}
      <section className="px-4 pb-2">
        <div className="mx-auto grid max-w-4xl gap-5 sm:grid-cols-2">
          <Reveal>
            <div className="h-full rounded-lg border border-border border-l-[3px] border-l-amber-500 bg-card p-6 shadow-sm">
              <div className="text-xs font-bold tracking-[0.06em] text-amber-700 uppercase">
                The problem
              </div>
              <p className="mt-2.5 text-base leading-relaxed">
                Each denial eats 30–60 minutes of staff time to fight. So most small practices just
                write them off — quietly losing revenue they&rsquo;re owed on every single one.
              </p>
            </div>
          </Reveal>
          <Reveal delay={120}>
            <div className="h-full rounded-lg border border-border border-l-[3px] border-l-blue-500 bg-card p-6 shadow-sm">
              <div className="text-xs font-bold tracking-[0.06em] text-blue-700 uppercase">
                The solution
              </div>
              <p className="mt-2.5 text-base leading-relaxed">
                Upload three documents. Heimdall reads them, classifies the denial, estimates the
                odds of a successful appeal, and drafts the letter — ready for your staff to review
                and send.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* How it works */}
      <section className="px-4 py-16">
        <div className="mx-auto max-w-5xl">
          <Reveal>
            <h2 className="text-center text-2xl font-extrabold tracking-tight sm:text-[26px]">
              How it works
            </h2>
          </Reveal>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <Reveal key={step.title} delay={i * 120}>
                <div className="h-full rounded-lg border border-border bg-card p-6 shadow-sm">
                  <div className="flex size-9 items-center justify-center rounded-[9px] bg-amber-500 text-base font-extrabold text-primary-foreground">
                    {i + 1}
                  </div>
                  <h3 className="mt-3.5 text-lg font-bold">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{step.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
          <p className="mt-7 text-center text-[15px] text-muted-foreground">
            Every clinical, financial, and submission decision stays with your practice.
          </p>
        </div>
      </section>
    </>
  );
}
