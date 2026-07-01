import Link from "next/link";

import { CtaLink } from "@/components/cta-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Wordmark } from "@/components/wordmark";
import { DEMO_MAILTO } from "@/lib/site";

export function MarketingHeader() {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
        <Link href="/" aria-label="Heimdall home" className="text-base">
          <Wordmark />
        </Link>
        <nav className="flex items-center gap-3 text-sm sm:gap-4">
          <Link
            href="/contact"
            className="hidden text-muted-foreground hover:text-foreground sm:inline"
          >
            Contact
          </Link>
          <Link href="/login" className="text-muted-foreground hover:text-foreground">
            Log in
          </Link>
          <ThemeToggle />
          <CtaLink href={DEMO_MAILTO} size="sm">
            Request a free demo
          </CtaLink>
        </nav>
      </div>
    </header>
  );
}
