"use client";

import { useEffect } from "react";

import { syncFavicon } from "@/lib/theme";

/**
 * Keeps the tab icon on the site's theme, not the OS one. The server picks the
 * initial set from the `hd_theme` cookie; this covers the cases it can't see —
 * a theme stored before the cookie existed, and Next re-rendering the icon
 * links on client navigation. Renders nothing.
 */
export function ThemeFavicon() {
  useEffect(() => {
    syncFavicon();
    const observer = new MutationObserver(() => syncFavicon());
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    observer.observe(document.head, { childList: true });
    return () => observer.disconnect();
  }, []);
  return null;
}
