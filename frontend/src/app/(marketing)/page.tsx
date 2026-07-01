import type { Metadata } from "next";

import { buttonVariants } from "@/components/ui/button";
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
      <a href={DEMO_MAILTO} className={buttonVariants({ size: "lg" })}>
        Request a free demo
      </a>
      <a href={GET_STARTED_MAILTO} className={buttonVariants({ variant: "outline", size: "lg" })}>
        Get started
      </a>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="mx-auto max-w-3xl px-4 pt-20 pb-16 text-center sm:pt-28">
        <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
          Stop writing off denied claims.
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
      </section>

      {/* Problem */}
      <section className="border-t bg-muted/30">
        <div className="mx-auto max-w-3xl px-4 py-16">
          <h2 className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
            The problem
          </h2>
          <p className="mt-3 text-xl leading-relaxed font-medium">
            Every denied claim takes 30–60 minutes of staff time to fight — find the claim, pull the
            notes, cite the right policy, write the letter. Most small practices just eat the denial,
            losing money they&rsquo;re owed.
          </p>
        </div>
      </section>

      {/* Solution */}
      <section>
        <div className="mx-auto max-w-3xl px-4 py-16">
          <h2 className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
            The solution
          </h2>
          <p className="mt-3 text-xl leading-relaxed font-medium">
            Upload three documents. Heimdall extracts the details, classifies the denial, estimates
            your odds of winning, and writes a payer-ready appeal letter you review, download, and
            send.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t bg-muted/30">
        <div className="mx-auto max-w-5xl px-4 py-16">
          <h2 className="text-center text-2xl font-semibold tracking-tight">How it works</h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-3">
            {STEPS.map((step, i) => (
              <div key={step.title}>
                <div className="flex size-9 items-center justify-center rounded-full border text-sm font-semibold">
                  {i + 1}
                </div>
                <h3 className="mt-4 font-medium">{step.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
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
      <section className="border-t">
        <div className="mx-auto max-w-3xl px-4 py-16 text-center">
          <h2 className="text-2xl font-semibold tracking-tight">See it on your own denials.</h2>
          <p className="mt-2 text-muted-foreground">
            A short walkthrough with your team — no commitment.
          </p>
          <div className="mt-6">
            <CtaButtons />
          </div>
        </div>
      </section>
    </>
  );
}
