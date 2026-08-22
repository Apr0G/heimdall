"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { fetchCase, fetchProcessingIds } from "@/lib/cases";
import { notifyUntilSeen } from "@/lib/notify";

/**
 * Watches the practice's in-flight appeals app-wide (independent of the page
 * you're on) and notifies when one finishes — so you hear "Your appeal for J.D.
 * is ready" even if you've navigated away. Renders nothing.
 */
export function ReadyNotifier() {
  const router = useRouter();
  const processingIds = useRef<Set<string>>(new Set());
  const primed = useRef(false);

  const { data } = useQuery({
    queryKey: ["watch-processing"],
    queryFn: () => fetchProcessingIds(),
    // Poll quickly while something is processing, slowly otherwise. Keep polling
    // in the background, and refetch on return so a finish is caught right away.
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? 3000 : 12000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (!data) return;
    const current = new Set(data);

    if (primed.current) {
      for (const id of processingIds.current) {
        // Was processing last poll, gone now -> it finished.
        if (!current.has(id)) void announce(id, router);
      }
    }
    processingIds.current = current;
    primed.current = true;
  }, [data, router]);

  return null;
}

async function announce(id: string, router: ReturnType<typeof useRouter>) {
  let status: string;
  let who: string;
  try {
    const c = await fetchCase(id);
    status = c.status;
    who = c.patient_initials ?? "your patient";
  } catch {
    return; // couldn't confirm; skip rather than guess
  }
  const open = () => router.push(`/cases/${id}`);

  if (status === "ready") {
    notifyUntilSeen("success", `Your appeal for ${who} is ready.`, open);
  } else if (status === "error") {
    notifyUntilSeen(
      "error",
      `We couldn't process the appeal for ${who}.`,
      open,
    );
  }
}
