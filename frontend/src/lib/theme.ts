/**
 * Theme state lives in three places on purpose: the `.dark` class (what CSS
 * reads), localStorage (what the pre-paint bootstrap script in app/layout.tsx
 * reads), and the `hd_theme` cookie (what the server reads to pick the favicon
 * set, since Safari only honours the icon in the initial HTML).
 */

export type Theme = "light" | "dark";

export const THEME_KEY = "heimdall_theme";
export const THEME_COOKIE = "hd_theme";
export const FAVICON_SIZES = [16, 32, 48] as const;

export function faviconHref(theme: Theme, size: number): string {
  return `/favicon-${theme}-${size}.png`;
}

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Point every favicon link at the given theme's set (Safari ignores this). */
export function syncFavicon(theme: Theme = currentTheme()): void {
  document
    .querySelectorAll<HTMLLinkElement>('link[rel="icon"]')
    .forEach((link) => {
      const next = link
        .getAttribute("href")
        ?.replace(/\/favicon-(?:light|dark)-/, `/favicon-${theme}-`);
      if (next && next !== link.getAttribute("href")) {
        link.setAttribute("href", next);
      }
    });
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // ignore storage failures (e.g. private mode)
  }
  // Not a credential: a one-word preference so SSR can render the matching
  // favicon. Lax + a year, no domain so it stays on this origin.
  document.cookie = `${THEME_COOKIE}=${theme}; path=/; max-age=31536000; samesite=lax${
    window.location.protocol === "https:" ? "; secure" : ""
  }`;
  syncFavicon(theme);
}
