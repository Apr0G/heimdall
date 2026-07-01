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

const STEPS = [
  {
    title: "Upload",
    body: "Add the denial (EOB/ERA), the original claim, and your clinical notes. PDF only.",
  },
  {
    title: "Review",
    body: "See the denial classified, the appeal deadline, and an estimated chance of success.",
  },
  {
    title: "Send",
    body: "Download the drafted appeal letter as a PDF and submit it to the payer.",
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
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-x-0 top-0 -z-10 h-72 bg-gradient-to-b from-amber-100/70 to-transparent dark:from-amber-500/10"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute top-4 -right-16 -z-10 size-72 rounded-full bg-blue-400/20 blur-3xl dark:bg-blue-500/10"
        />
        <div className="mx-auto max-w-3xl px-4 pt-20 pb-20 text-center sm:pt-28">
          <span className="inline-flex items-center gap-2 rounded-full border border-amber-300/70 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/40 dark:text-amber-200">
            <span className="size-1.5 rounded-full bg-amber-500" />
            Built for small US practices
          </span>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Stop writing off{" "}
            <span className="text-amber-500 dark:text-amber-400">denied claims</span>.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
            Heimdall reads your insurance denial, tells you whether it&rsquo;s worth appealing, and
            drafts a payer-ready appeal letter — so your practice recovers revenue it already earned.
          </p>
          <div className="mt-8">
            <CtaButtons />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Free demo, no commitment — get started when you&rsquo;re ready.
          </p>
        </div>
      </section>

      {/* Problem */}
      <section className="border-t bg-muted/30">
        <div className="mx-auto max-w-3xl px-4 py-16">
          <div className="border-l-2 border-amber-400 pl-5">
            <p className="text-xs font-semibold tracking-wider text-amber-600 uppercase dark:text-amber-400">
              The problem
            </p>
            <p className="mt-3 text-xl leading-relaxed font-medium text-foreground">
              Every denied claim takes 30–60 minutes of staff time to fight — find the claim, pull
              the notes, cite the right policy, write the letter. Most small practices just eat the
              denial, losing money they&rsquo;re owed.
            </p>
          </div>
        </div>
      </section>

      {/* Solution */}
      <section>
        <div className="mx-auto max-w-3xl px-4 py-16">
          <div className="border-l-2 border-blue-500 pl-5">
            <p className="text-xs font-semibold tracking-wider text-blue-600 uppercase dark:text-blue-400">
              The solution
            </p>
            <p className="mt-3 text-xl leading-relaxed font-medium text-foreground">
              Upload three documents. Heimdall extracts the details, classifies the denial, estimates
              your odds of winning, and writes a payer-ready appeal letter you review, download, and
              send.
            </p>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t bg-muted/30">
        <div className="mx-auto max-w-5xl px-4 py-16">
          <div className="mx-auto max-w-xl text-center">
            <p className="text-xs font-semibold tracking-wider text-blue-600 uppercase dark:text-blue-400">
              How it works
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">
              From denial to appeal in three steps
            </h2>
          </div>
          <div className="mt-10 grid gap-6 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <div
                key={step.title}
                className="rounded-xl border bg-background p-6 transition-colors hover:border-amber-300"
              >
                <div className="flex size-9 items-center justify-center rounded-full bg-amber-400 text-sm font-bold text-amber-950">
                  {i + 1}
                </div>
                <h3 className="mt-4 font-medium">{step.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Assurance */}
      <section>
        <div className="mx-auto max-w-3xl px-4 py-12 text-center">
          <p className="text-base text-muted-foreground">
            Built for healthcare from day one. Every clinical, financial, and submission decision
            stays with your practice.
          </p>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="px-4 pt-4 pb-20">
        <div className="mx-auto max-w-4xl rounded-2xl border bg-gradient-to-br from-amber-50 to-blue-50 px-6 py-14 text-center dark:from-amber-950/30 dark:to-blue-950/30">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            See it on your own denials.
          </h2>
          <p className="mx-auto mt-2 max-w-md text-muted-foreground">
            A short walkthrough with your team — no commitment.
          </p>
          <div className="mt-7">
            <CtaButtons />
          </div>
        </div>
      </section>
    </>
  );
}
