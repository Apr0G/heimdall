import Image from "next/image";

import wordmarkOnDark from "@/assets/brand/wordmark-on-dark.png";
import wordmarkOnLight from "@/assets/brand/wordmark-on-light.png";
import { cn } from "@/lib/utils";

/**
 * Brand wordmark (amber arc + HEIMDALL). Two exports with baked-in text colour,
 * swapped via the `.dark` class, and sized in em so a caller's `text-*` class
 * scales it the same way it scaled the old text-only mark. `sizes` keeps the
 * srcset around the rendered ~15rem instead of the 2000px source.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center", className)}>
      <Image
        src={wordmarkOnLight}
        alt="Heimdall"
        priority
        sizes="16rem"
        className="h-[1.5em] w-auto dark:hidden"
      />
      <Image
        src={wordmarkOnDark}
        alt="Heimdall"
        priority
        sizes="16rem"
        className="hidden h-[1.5em] w-auto dark:block"
      />
    </span>
  );
}
