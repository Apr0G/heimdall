"use client";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function SiteHeader() {
  const { user, logout } = useAuth();

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <span className="font-semibold tracking-tight">Heimdall</span>
        <div className="flex items-center gap-3 text-sm">
          {user && <span className="text-muted-foreground">{user.email}</span>}
          <Button variant="outline" size="sm" onClick={logout}>
            Log out
          </Button>
        </div>
      </div>
    </header>
  );
}
