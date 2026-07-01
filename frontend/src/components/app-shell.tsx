"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Disclaimer } from "@/components/disclaimer";
import { ReadyNotifier } from "@/components/ready-notifier";
import { SiteHeader } from "@/components/site-header";
import { useAuth } from "@/lib/auth-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading } = useAuth();

  // Safety net for when the presence cookie and the stored token disagree
  // (e.g. token cleared out-of-band): force unauthenticated users to /login.
  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

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
