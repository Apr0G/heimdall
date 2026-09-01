import type { Metadata } from "next";

import { CtaLink } from "@/components/cta-link";
import { HeroPreview } from "@/components/hero-preview";
import { Reveal } from "@/components/reveal";

export const metadata: Metadata = {
  description:
    "Heimdall checks your claims for denial risk before you submit, and when a payer still says no, it analyzes the denial and drafts a payer-ready appeal letter.",
  openGraph: {
    title: "Heimdall Claims | Catch denials before they happen",
    description:
      "Pre-check a draft claim for denial risk, or upload a denial and get a drafted appeal. Built for small US practices.",
    type: "website",
  },
};

const HERO_BG = {
  backgroundImage:
    "radial-gradient(120% 90% at 20% 0%, color-mix(in oklab, var(--color-amber-500) 20%, transparent), transparent 60%), radial-gradient(120% 90% at 90% 20%, color-mix(in oklab, var(--color-blue-500) 18%, transparent), transparent 55%)",
};

// The hero aurora mirrored vertically, so the closing band glows up from the
// bottom edge and bookends the page.
const CTA_BG = {
  backgroundImage:
    "radial-gradient(130% 160% at 20% 100%, color-mix(in oklab, var(--color-amber-500) 24%, transparent), transparent 75%), radial-gradient(130% 150% at 90% 100%, color-mix(in oklab, var(--color-blue-500) 21%, transparent), transparent 70%)",
  // The ellipses are taller than the section, so without this the glow gets
  // clipped into a hard seam at the section's top edge.
  maskImage: "linear-gradient(to top, black 45%, transparent 100%)",
  WebkitMaskImage: "linear-gradient(to top, black 45%, transparent 100%)",
};

// Semi-transparent foreground for the lines, not the opaque border token: an
// opaque gray flips from lighter-than to darker-than its surroundings wherever
// the aurora glow raises the background, which reads as two different colors.
const GRID_LINE =
  "color-mix(in oklab, var(--color-foreground) 9%, transparent)";

const HERO_GRID = {
  backgroundImage: `linear-gradient(to right, ${GRID_LINE} 1px, transparent 1px), linear-gradient(to bottom, ${GRID_LINE} 1px, transparent 1px)`,
  backgroundSize: "48px 48px",
  maskImage:
    "radial-gradient(ellipse 90% 70% at 50% 0%, black, transparent 72%)",
  WebkitMaskImage:
    "radial-gradient(ellipse 90% 70% at 50% 0%, black, transparent 72%)",
};

// The hero grid flipped: densest at the bottom edge, dissolving upward.
const CTA_GRID = {
  backgroundImage: `linear-gradient(to right, ${GRID_LINE} 1px, transparent 1px), linear-gradient(to bottom, ${GRID_LINE} 1px, transparent 1px)`,
  backgroundSize: "48px 48px",
  maskImage:
    "radial-gradient(ellipse 90% 70% at 50% 100%, black, transparent 72%)",
  WebkitMaskImage:
    "radial-gradient(ellipse 90% 70% at 50% 100%, black, transparent 72%)",
};

const STEPS = [
  {
    title: "Upload",
    body: "Before submitting: the draft claim and clinical notes. After a denial: the denial/EOB, the claim, and the notes. PDF only.",
  },
  {
    title: "Review",
    body: "A risk report with flags and suggested fixes, or the denial breakdown, success estimate, and drafted appeal letter.",
  },
  {
    title: "Act",
    body: "Fix the claim while it's still fixable, or download the appeal PDF and send it. Log outcomes to sharpen future odds.",
  },
];

const PRECHECK_POINTS = [
  "Runs your codes through CMS's own bundling and unit edits (NCCI)",
  "AI reads the clinical note against every billed code, a check no scrubber does",
  "Each flag names the denial it predicts and a concrete fix",
];

const APPEAL_POINTS = [
  "Classifies the denial and tells you if it's worth fighting",
  "Estimates your odds of overturning it before you spend staff time",
  "Drafts the payer-ready letter for your staff to review and send",
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
        <div
          aria-hidden
          style={HERO_GRID}
          className="pointer-events-none absolute inset-0 -z-10"
        />
        <div className="relative mx-auto max-w-3xl">
          <div
            aria-hidden
            className="animate-hero-float pointer-events-none absolute top-2 -left-24 hidden -rotate-4 min-[900px]:block lg:-left-28 xl:-left-44"
          >
            <div className="rounded-lg border border-border bg-card px-3.5 py-2.5 text-left shadow-md">
              <div className="flex items-center gap-2 text-xs font-semibold">
                <span className="size-1.5 rounded-full bg-amber-500" />
                CO-97 · bundling risk
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                Caught before submission
              </div>
            </div>
          </div>
          <div
            aria-hidden
            className="animate-hero-float-late pointer-events-none absolute top-28 -right-24 hidden rotate-3 min-[900px]:block lg:-right-28 xl:-right-44"
          >
            <div className="rounded-lg border border-border bg-card px-3.5 py-2.5 text-left shadow-md">
              <div className="flex items-center gap-2 text-xs font-semibold">
                <span className="size-1.5 rounded-full bg-blue-500" />
                Appeal drafted
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                Ready for review
              </div>
            </div>
          </div>
          <h1 className="mx-auto max-w-3xl text-4xl font-extrabold tracking-tight text-balance sm:text-[52px] sm:leading-[1.03]">
            Catch denials <span className="text-amber-600">before</span> they
            happen.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted-foreground">
            Heimdall pre-checks your claims for denial risk while you can still
            fix them. When a payer says no anyway, it drafts the appeal letter.
            Minutes, not staff-hours.
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
            <div className="h-full rounded-lg border border-border border-l-[3px] border-l-amber-500 bg-card p-6 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">
              <div className="text-xs font-bold tracking-[0.06em] text-amber-700 uppercase">
                The problem
              </div>
              <p className="mt-2.5 text-base leading-relaxed">
                Around one claim in ten comes back denied, and most of those
                denials were preventable. Each one eats 30–60 minutes of staff
                time to fight, so small practices quietly write off revenue
                they&rsquo;re owed, twice: once at submission, once at denial.
              </p>
            </div>
          </Reveal>
          <Reveal delay={120}>
            <div className="h-full rounded-lg border border-border border-l-[3px] border-l-blue-500 bg-card p-6 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">
              <div className="text-xs font-bold tracking-[0.06em] text-blue-700 uppercase">
                The solution
              </div>
              <p className="mt-2.5 text-base leading-relaxed">
                Work the denial at both ends. Pre-check flags the claims a payer
                is likely to bounce, with the fix, while the claim is still on
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
                footer="Risk flags, not guarantees, checked against the Medicare (NCCI) edit baseline."
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
            No EHR integration to install, no clearinghouse contract. Upload
            PDFs, get answers.
          </p>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="relative overflow-hidden px-4 pt-32 pb-24 text-center">
        <div
          aria-hidden
          style={CTA_BG}
          className="pointer-events-none absolute inset-0 -z-10"
        />
        <div
          aria-hidden
          style={CTA_GRID}
          className="pointer-events-none absolute inset-0 -z-10"
        />
        <Reveal className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            Your next denial is preventable.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-[15px] text-muted-foreground">
            Set up your practice and pre-check the next claim before the payer
            ever sees it.
          </p>
          <div className="mt-6 flex justify-center">
            <CtaLink href="/get-started" size="lg">
              Get started
            </CtaLink>
          </div>
        </Reveal>
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
      className={`flex h-full flex-col rounded-lg border border-border ${border} border-t-[3px] bg-card p-6 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md`}
    >
      <div className={`text-xs font-bold tracking-[0.06em] uppercase ${text}`}>
        {eyebrow}
      </div>
      <h3 className="mt-1.5 text-xl font-extrabold tracking-tight">{title}</h3>
      <ul className="mt-4 mb-5 space-y-2.5">
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
