"use client";

// Route-level error boundary. Without one, any render throw unmounts the whole
// tree to Next's generic error page — no branding, no way back, and no reset.
//
// PHI: we deliberately render NOTHING from the error itself. Production builds
// already reduce a server error to an opaque digest, but a client-side throw can
// carry a message built from case data, and this component is the last place that
// would be shown to (and screenshotted by) a user.

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Console only, and only the digest — never `error.message`, which is exactly
    // the kind of string that quietly carries a patient name or claim number.
    console.error("Unhandled UI error", error.digest ?? "(no digest)");
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 py-24 text-center">
      <span
        className="mb-5 flex size-[52px] items-center justify-center rounded-full text-2xl font-bold"
        style={{
          background:
            "color-mix(in oklab, var(--destructive) 14%, var(--card))",
          color: "var(--destructive)",
        }}
        aria-hidden
      >
        !
      </span>
      <h1 className="mb-2 text-xl font-extrabold tracking-tight">
        Something went wrong
      </h1>
      <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
        This page didn&rsquo;t load. Your data is safe — nothing was changed.
        Try again, and if it keeps happening, contact support.
      </p>
      {error.digest ? (
        <p className="mt-3 font-mono text-xs text-muted-foreground">
          Reference: {error.digest}
        </p>
      ) : null}
      <div className="mt-6">
        <Button onClick={reset}>Try again</Button>
      </div>
    </div>
  );
}
