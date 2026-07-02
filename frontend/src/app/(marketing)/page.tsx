import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { DEMO_MAILTO, GET_STARTED_MAILTO } from "@/lib/site";

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

const CTA_CARD_BG = {
  backgroundImage:
    "linear-gradient(120deg, color-mix(in oklab, var(--color-amber-500) 22%, var(--card)), color-mix(in oklab, var(--color-blue-500) 20%, var(--card)))",
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

function CtaButtons() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <CtaLink href={DEMO_MAILTO} size="lg">
        Request a free demo
      </CtaLink>
      <CtaLink href={GET_STARTED_MAILTO} variant="secondary" size="lg">
        Get started
      </CtaLink>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section style={HERO_BG} className="px-4 pt-20 pb-20 text-center sm:pt-28">
        <div className="mx-auto max-w-3xl">
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
          <div className="mt-8">
            <CtaButtons />
          </div>
          <p className="mt-4 text-[13px] text-muted-foreground">Free demo, no commitment.</p>
        </div>
      </section>

      {/* Problem / Solution */}
      <section className="px-4 pb-2">
        <div className="mx-auto grid max-w-4xl gap-5 sm:grid-cols-2">
          <div className="rounded-lg border border-border border-l-[3px] border-l-amber-500 bg-card p-6 shadow-sm">
            <div className="text-xs font-bold tracking-[0.06em] text-amber-700 uppercase">
              The problem
            </div>
            <p className="mt-2.5 text-base leading-relaxed">
              Each denial eats 30–60 minutes of staff time to fight. So most small practices just
              write them off — quietly losing revenue they&rsquo;re owed on every single one.
            </p>
          </div>
          <div className="rounded-lg border border-border border-l-[3px] border-l-blue-500 bg-card p-6 shadow-sm">
            <div className="text-xs font-bold tracking-[0.06em] text-blue-700 uppercase">
              The solution
            </div>
            <p className="mt-2.5 text-base leading-relaxed">
              Upload three documents. Heimdall reads them, classifies the denial, estimates the odds
              of a successful appeal, and drafts the letter — ready for your staff to review and
              send.
            </p>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="px-4 py-16">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center text-2xl font-extrabold tracking-tight sm:text-[26px]">
            How it works
          </h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <div key={step.title} className="rounded-lg border border-border bg-card p-6 shadow-sm">
                <div className="flex size-9 items-center justify-center rounded-[9px] bg-amber-500 text-base font-extrabold text-primary-foreground">
                  {i + 1}
                </div>
                <h3 className="mt-3.5 text-lg font-bold">{step.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{step.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-7 text-center text-[15px] text-muted-foreground">
            Every clinical, financial, and submission decision stays with your practice.
          </p>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="px-4 pb-20">
        <div
          style={CTA_CARD_BG}
          className="mx-auto max-w-4xl rounded-2xl border border-border px-6 py-12 text-center"
        >
          <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            Recover what you&rsquo;re owed.
          </h2>
          <p className="mx-auto mt-2.5 max-w-md text-base text-foreground/80">
            See Heimdall on your own denials in a free demo.
          </p>
          <div className="mt-6">
            <CtaButtons />
          </div>
        </div>
      </section>
    </>
  );
}
