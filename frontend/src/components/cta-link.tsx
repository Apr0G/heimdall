import { cn } from "@/lib/utils";

const VARIANTS = {
  // Amber is the brand accent; blue shows up in gradients/section markers.
  primary: "bg-amber-400 text-amber-950 shadow-sm hover:bg-amber-300 focus-visible:ring-amber-500",
  secondary:
    "border border-border bg-background text-foreground hover:bg-muted focus-visible:ring-ring",
};

const SIZES = {
  sm: "px-3.5 py-2 text-sm",
  md: "px-5 py-2.5 text-sm",
  lg: "px-6 py-3 text-base",
};

/** A colored call-to-action link (renders an <a>, so it works for mailto). */
export function CtaLink({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      className={cn(
        "inline-flex items-center justify-center rounded-lg font-semibold transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none",
        SIZES[size],
        VARIANTS[variant],
        className,
      )}
    >
      {children}
    </a>
  );
}
