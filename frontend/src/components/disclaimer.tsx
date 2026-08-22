import { cn } from "@/lib/utils";

// The exact legal disclaimer required on every page that shows the success
// probability or the appeal letter (Phase 13). Rendered app-wide in the footer.
export const DISCLAIMER_TEXT =
  "Heimdall provides AI-assisted estimates and drafts. All clinical, financial, and submission decisions remain with the practice. Heimdall is not a medical, legal, or billing advisor.";

export function Disclaimer({ className }: { className?: string }) {
  return (
    <p
      className={cn("text-xs leading-relaxed text-muted-foreground", className)}
    >
      {DISCLAIMER_TEXT}
    </p>
  );
}
