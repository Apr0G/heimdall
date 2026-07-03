"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { Disclaimer } from "@/components/disclaimer";
import { ReadyNotifier } from "@/components/ready-notifier";
import { SiteHeader } from "@/components/site-header";
import { useAuth } from "@/lib/auth-context";
import { useIdleLogout } from "@/lib/use-idle-logout";

// HIPAA automatic logoff — sign out after 15 minutes of inactivity.
const IDLE_LOGOUT_MS = 15 * 60 * 1000;

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  // Safety net for when the presence cookie and the stored token disagree
  // (e.g. token cleared out-of-band): force unauthenticated users to /login.
  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  useIdleLogout(IDLE_LOGOUT_MS, () => {
    if (user) {
      toast.message("Signed out for inactivity.");
      logout();
    }
  });

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <ReadyNotifier />
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
      <footer className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-4">
          <Disclaimer />
        </div>
      </footer>
    </div>
  );
}
