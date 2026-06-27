"use client";

import { Button } from "@/components/ui/button";

const THEME_KEY = "heimdall_theme";

export function ThemeToggle() {
  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      window.localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    } catch {
      // ignore storage failures (e.g. private mode)
    }
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
