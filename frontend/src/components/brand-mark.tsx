import { useId } from "react";

import { cn } from "@/lib/utils";

/** The arc's amber gradient, shared with the wordmark so the two always match. */
export function ArcGradient({ id }: { id: string }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0.24" stopColor="#AB5E0C" />
      <stop offset="0.86" stopColor="#E7A132" />
    </linearGradient>
  );
}

export const ARC_PATH =
  "M1330.16 654.379C1244.53 654.379 1158.89 654.379 1073.26 654.379C1068.63 635.602 1069.51 614.882 1067.66 595.435C1065.45 571.964 1060.22 548.025 1054.35 525.225C1026.15 415.652 964.895 315.4 876.781 243.581C651.298 59.8086 319.26 105.81 148.061 339.206C100.114 404.554 66.1494 482.006 52.8383 562.04C47.7419 592.618 48.1444 623.599 43.9197 654.177C29.4016 654.177 14.85 654.177 0.331965 654.177C-2.2833 593.993 10.8935 531.193 27.8927 473.959C121.64 158.149 438.925 -42.1196 764.66 7.53684C1086.37 56.5563 1322.95 329.818 1330.16 654.379Z";

/** The arc alone (no text), for spaces too narrow for the full wordmark. */
export function BrandMark({ className }: { className?: string }) {
  // Gradient ids are document-global; two marks on one page must not share one.
  const id = useId();
  return (
    <svg
      viewBox="0 0 1331 655"
      role="img"
      aria-label="Heimdall"
      className={cn("h-[1em] w-auto", className)}
    >
      <defs>
        <ArcGradient id={id} />
      </defs>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d={ARC_PATH}
        fill={`url(#${id})`}
      />
    </svg>
  );
}
