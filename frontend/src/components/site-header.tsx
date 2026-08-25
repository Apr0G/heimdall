"use client";

import { SettingsIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button, buttonVariants } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";
import { homePath, useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

function NavTab({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-full px-3.5 py-1 font-medium transition-colors",
        active
          ? "bg-card text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

export function SiteHeader() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const onSettings = pathname.startsWith("/settings");

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-5">
          <Link href={homePath(user?.role)} aria-label="Heimdall home">
            <Wordmark />
          </Link>
          {user && user.role !== "admin" && (
            // Segmented control: the active product area reads as a raised pill;
            // the inactive one stays quiet but clearly clickable.
            <nav
              aria-label="Product areas"
              className="flex items-center gap-0.5 rounded-full border border-border bg-muted p-[3px] text-sm"
            >
              <NavTab
                href="/dashboard"
                active={
                  pathname.startsWith("/dashboard") ||
                  pathname.startsWith("/cases")
                }
              >
                Appeals
              </NavTab>
              <NavTab
                href="/pre-checks"
                active={pathname.startsWith("/pre-checks")}
              >
                Pre-checks
              </NavTab>
            </nav>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm">
          {user?.role === "admin" && (
            <Link
              href="/admin"
              className="mr-1 text-muted-foreground hover:text-foreground"
            >
              Admin
            </Link>
          )}
          <ThemeToggle />
          {user && (
            // A real button, not a bare email link: the gear is the universal
            // "settings" cue, and the email makes clear whose account it opens.
            <Link
              href="/settings"
              aria-label="Account settings"
              aria-current={onSettings ? "page" : undefined}
              title={user.email}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "max-w-[14rem]",
                onSettings && "bg-muted text-foreground",
              )}
            >
              <SettingsIcon aria-hidden />
              <span className="hidden truncate sm:inline">{user.email}</span>
              <span className="sm:hidden">Account</span>
            </Link>
          )}
          <Button variant="outline" size="sm" onClick={logout}>
            Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
