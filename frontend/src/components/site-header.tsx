"use client";

import { SettingsIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button, buttonVariants } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";
import { homePath, useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

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
            <nav className="flex items-center gap-4 text-sm">
              <Link
                href="/dashboard"
                aria-current={
                  pathname.startsWith("/dashboard") ||
                  pathname.startsWith("/cases")
                    ? "page"
                    : undefined
                }
                className={cn(
                  "text-muted-foreground hover:text-foreground",
                  (pathname.startsWith("/dashboard") ||
                    pathname.startsWith("/cases")) &&
                    "font-semibold text-foreground",
                )}
              >
                Appeals
              </Link>
              <Link
                href="/pre-checks"
                aria-current={
                  pathname.startsWith("/pre-checks") ? "page" : undefined
                }
                className={cn(
                  "text-muted-foreground hover:text-foreground",
                  pathname.startsWith("/pre-checks") &&
                    "font-semibold text-foreground",
                )}
              >
                Pre-checks
              </Link>
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
