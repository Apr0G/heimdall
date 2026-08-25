import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { HeroPreview } from "@/components/hero-preview";
import { Reveal } from "@/components/reveal";

export const metadata: Metadata = {
  title: "Heimdall — Catch denials before they happen",
  description:
    "Heimdall checks your claims for denial risk before you submit — and when a payer still says no, it analyzes the denial and drafts a payer-ready appeal letter.",
  openGraph: {
    title: "Heimdall — Catch denials before they happen",
    description:
      "Pre-check a draft claim for denial risk, or upload a denial and get a drafted appeal. Built for small US practices.",
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
    body: "Before submitting: the draft claim and clinical notes. After a denial: the denial/EOB, the claim, and the notes. PDF only.",
  },
  {
    title: "Review",
    body: "A risk report with flags and suggested fixes — or the denial breakdown, success estimate, and drafted appeal letter.",
  },
  {
    title: "Act",
    body: "Fix the claim while it's still fixable, or download the appeal PDF and send it. Log outcomes to sharpen future odds.",
  },
];

const PRECHECK_POINTS = [
  "Runs your codes through CMS's own bundling and unit edits (NCCI)",
  "AI reads the clinical note against every billed code — the check no scrubber does",
  "Each flag names the denial it predicts and a concrete fix",
];

const APPEAL_POINTS = [
  "Classifies the denial and tells you if it's worth fighting",
  "Estimates your odds of overturning it before you spend staff time",
  "Drafts the payer-ready letter — your staff reviews and sends",
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
            Catch denials <span className="text-amber-600">before</span> they
            happen.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted-foreground">
            Heimdall pre-checks your claims for denial risk while you can still
            fix them — and when a payer says no anyway, it drafts the appeal
            letter. Minutes, not staff-hours.
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
                Around one claim in ten comes back denied — and most of those
                denials were preventable. Each one eats 30–60 minutes of staff
                time to fight, so small practices quietly write off revenue
                they&rsquo;re owed, twice: once at submission, once at denial.
              </p>
            </div>
          </Reveal>
          <Reveal delay={120}>
            <div className="h-full rounded-lg border border-border border-l-[3px] border-l-blue-500 bg-card p-6 shadow-sm">
              <div className="text-xs font-bold tracking-[0.06em] text-blue-700 uppercase">
                The solution
              </div>
              <p className="mt-2.5 text-base leading-relaxed">
                Work the denial at both ends. Pre-check flags the claims a payer
                is likely to bounce — with the fix — while the claim is still on
                your desk. And for the denials that come anyway, Heimdall reads
                the paperwork and drafts the appeal.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Two moments, one workflow */}
      <section className="px-4 pt-16">
        <div className="mx-auto max-w-5xl">
          <Reveal>
            <h2 className="text-center text-2xl font-extrabold tracking-tight sm:text-[26px]">
              Two moments, one workflow
            </h2>
            <p className="mx-auto mt-2 max-w-xl text-center text-[15px] text-muted-foreground">
              The same documents your practice already has, working at the two
              points where denials are won or lost.
            </p>
          </Reveal>
          <div className="mt-8 grid gap-5 sm:grid-cols-2">
            <Reveal>
              <FeatureCard
                accent="amber"
                eyebrow="Before you submit"
                title="Pre-check"
                points={PRECHECK_POINTS}
                footer="Risk flags, not guarantees — checked against the Medicare (NCCI) edit baseline."
              />
            </Reveal>
            <Reveal delay={120}>
              <FeatureCard
                accent="blue"
                eyebrow="After a denial"
                title="Appeals"
                points={APPEAL_POINTS}
                footer="Every clinical, financial, and submission decision stays with your practice."
              />
            </Reveal>
          </div>
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
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    {step.body}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
          <p className="mt-7 text-center text-[15px] text-muted-foreground">
            No EHR integration to install, no clearinghouse contract — upload
            PDFs, get answers.
          </p>
        </div>
      </section>
    </>
  );
}

function FeatureCard({
  accent,
  eyebrow,
  title,
  points,
  footer,
}: {
  accent: "amber" | "blue";
  eyebrow: string;
  title: string;
  points: string[];
  footer: string;
}) {
  const border =
    accent === "amber" ? "border-t-amber-500" : "border-t-blue-500";
  const text = accent === "amber" ? "text-amber-700" : "text-blue-700";
  const dot = accent === "amber" ? "bg-amber-500" : "bg-blue-500";
  return (
    <div
      className={`flex h-full flex-col rounded-lg border border-border ${border} border-t-[3px] bg-card p-6 shadow-sm`}
    >
      <div className={`text-xs font-bold tracking-[0.06em] uppercase ${text}`}>
        {eyebrow}
      </div>
      <h3 className="mt-1.5 text-xl font-extrabold tracking-tight">{title}</h3>
      <ul className="mt-4 space-y-2.5">
        {points.map((point) => (
          <li key={point} className="flex items-start gap-2.5 text-sm">
            <span
              aria-hidden
              className={`mt-1.5 size-1.5 shrink-0 rounded-full ${dot}`}
            />
            <span className="leading-relaxed">{point}</span>
          </li>
        ))}
      </ul>
      <p className="mt-auto border-t border-border pt-3.5 text-xs leading-relaxed text-muted-foreground">
        {footer}
      </p>
    </div>
  );
}
