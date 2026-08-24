"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { fetchCase, fetchProcessingItems } from "@/lib/cases";
import { notifyUntilSeen } from "@/lib/notify";

/**
 * Watches the practice's in-flight cases app-wide (independent of the page
 * you're on) and notifies when one finishes — "Your appeal for J.D. is ready" /
 * "Your pre-check for J.D. is ready" — even if you've navigated away.
 * Renders nothing.
 */
export function ReadyNotifier() {
  const router = useRouter();
  const processing = useRef<Map<string, string>>(new Map());
  const primed = useRef(false);

  const { data } = useQuery({
    queryKey: ["watch-processing"],
    queryFn: () => fetchProcessingItems(),
    // Poll quickly while something is processing, slowly otherwise. Keep polling
    // in the background, and refetch on return so a finish is caught right away.
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? 3000 : 12000,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (!data) return;
    const current = new Map(data.map((item) => [item.id, item.case_type]));

    if (primed.current) {
      for (const [id, caseType] of processing.current) {
        // Was processing last poll, gone now -> it finished.
        if (!current.has(id)) void announce(id, caseType, router);
      }
    }
    processing.current = current;
    primed.current = true;
  }, [data, router]);

  return null;
}

async function announce(
  id: string,
  caseType: string,
  router: ReturnType<typeof useRouter>,
) {
  let status: string;
  let who: string;
  try {
    const c = await fetchCase(id);
    status = c.status;
    who = c.patient_initials ?? "your patient";
  } catch {
    return; // couldn't confirm; skip rather than guess
  }
  const isPreCheck = caseType === "pre_check";
  const noun = isPreCheck ? "pre-check" : "appeal";
  const open = () =>
    router.push(isPreCheck ? `/pre-checks/${id}` : `/cases/${id}`);

  if (status === "ready") {
    notifyUntilSeen("success", `Your ${noun} for ${who} is ready.`, open);
  } else if (status === "error") {
    notifyUntilSeen(
      "error",
      `We couldn't process the ${noun} for ${who}.`,
      open,
    );
  }
}
