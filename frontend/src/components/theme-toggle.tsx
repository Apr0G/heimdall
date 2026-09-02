"use client";

import { Button } from "@/components/ui/button";
import { applyTheme, currentTheme } from "@/lib/theme";

export function ThemeToggle() {
  function toggle() {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  }

  return (
    <Button
      variant="outline"
      size="icon-sm"
      onClick={toggle}
      aria-label="Toggle theme"
      title="Toggle theme"
    >
      {/* The current theme is reflected purely via the `.dark` class — no React
          state, so there's no hydration flash. */}
      <span className="hidden dark:inline" aria-hidden>
        ☀
      </span>
      <span className="dark:hidden" aria-hidden>
        ☾
      </span>
    </Button>
  );
}
