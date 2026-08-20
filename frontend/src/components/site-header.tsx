"use client";

import { UserRoundIcon } from "lucide-react";
import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";
import { useAuth } from "@/lib/auth-context";

export function SiteHeader() {
  const { user, logout } = useAuth();

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/dashboard" aria-label="Heimdall dashboard">
          <Wordmark />
        </Link>
        <div className="flex items-center gap-3 text-sm">
          {user?.role === "admin" && (
            <Link
              href="/admin"
              className="text-muted-foreground hover:text-foreground"
            >
              Admin
            </Link>
          )}
          {user && (
            <Link
              href="/settings"
              title="Account settings"
              className="hidden max-w-[16rem] truncate text-muted-foreground hover:text-foreground sm:inline"
            >
              {user.email}
            </Link>
          )}
          <Link
            href="/settings"
            aria-label="Account settings"
            className="text-muted-foreground hover:text-foreground sm:hidden"
          >
            <UserRoundIcon className="size-4" />
          </Link>
          <ThemeToggle />
          <Button variant="outline" size="sm" onClick={logout}>
            Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
