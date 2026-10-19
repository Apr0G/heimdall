import Link from "next/link";

import { Disclaimer } from "@/components/disclaimer";
import { Wordmark } from "@/components/wordmark";
import { COMPANY_LEGAL_NAME } from "@/lib/site";

export function MarketingFooter() {
  return (
    <footer className="border-t">
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-10">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Link href="/" aria-label="Heimdall home" className="flex">
            <Wordmark />
          </Link>
          <nav className="flex flex-wrap gap-4 text-sm text-muted-foreground">
            <Link href="/contact" className="hover:text-foreground">
              Contact
            </Link>
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
            <Link href="/privacy" className="hover:text-foreground">
              Privacy
            </Link>
            <Link href="/subprocessors" className="hover:text-foreground">
              Subprocessors
            </Link>
            <Link href="/login" className="hover:text-foreground">
              Log in
            </Link>
          </nav>
        </div>
        <Disclaimer />
        <p className="text-xs text-muted-foreground">
          © {new Date().getFullYear()} {COMPANY_LEGAL_NAME} All rights reserved.
        </p>
      </div>
    </footer>
  );
}
