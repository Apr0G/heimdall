import Link from "next/link";

import { CtaLink } from "@/components/cta-link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Wordmark } from "@/components/wordmark";

/** `showLogin` is false on the login page itself (a Login button there is redundant). */
export function MarketingHeader({ showLogin = true }: { showLogin?: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
        <Link href="/" aria-label="Heimdall home" className="flex text-base">
          <Wordmark />
        </Link>
        <nav className="flex items-center gap-3 text-sm sm:gap-4">
          <ThemeToggle />
          {showLogin && (
            <CtaLink href="/login" size="sm">
              Login
            </CtaLink>
          )}
        </nav>
      </div>
    </header>
  );
}
