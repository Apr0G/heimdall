import Link from "next/link";

import { Wordmark } from "@/components/wordmark";
import { buttonVariants } from "@/components/ui/button";
import { DEMO_MAILTO } from "@/lib/site";

export function MarketingHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
        <Link href="/" aria-label="Heimdall home" className="text-base">
          <Wordmark />
        </Link>
        <nav className="flex items-center gap-3 text-sm sm:gap-5">
          <Link
            href="/contact"
            className="hidden text-muted-foreground hover:text-foreground sm:inline"
          >
            Contact
          </Link>
          <Link href="/login" className="text-muted-foreground hover:text-foreground">
            Log in
          </Link>
          <a href={DEMO_MAILTO} className={buttonVariants({ size: "sm" })}>
            Request a free demo
          </a>
        </nav>
      </div>
    </header>
  );
}
