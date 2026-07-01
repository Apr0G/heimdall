import { buttonVariants } from "@/components/ui/button";
import { DEMO_MAILTO } from "@/lib/site";

export default function LandingPage() {
  return (
    <section className="mx-auto max-w-3xl px-4 py-24 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">Stop writing off denied claims.</h1>
      <p className="mt-4 text-lg text-muted-foreground">
        Heimdall reads your denial, tells you if it&rsquo;s worth appealing, and drafts the
        appeal letter.
      </p>
      <div className="mt-8">
        <a href={DEMO_MAILTO} className={buttonVariants()}>
          Request a free demo
        </a>
      </div>
    </section>
  );
}
