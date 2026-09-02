import { beforeEach, describe, expect, it } from "vitest";

import { applyTheme, syncFavicon } from "./theme";

function addIcon(href: string) {
  const link = document.createElement("link");
  link.rel = "icon";
  link.href = href;
  document.head.appendChild(link);
  return link;
}

describe("theme", () => {
  beforeEach(() => {
    document.head.innerHTML = "";
    document.documentElement.className = "";
    document.cookie = "hd_theme=; path=/; max-age=0";
    window.localStorage.clear();
  });

  it("applyTheme sets the class, storage, cookie and favicons together", () => {
    const icon = addIcon("/favicon-dark-32.png");
    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(window.localStorage.getItem("heimdall_theme")).toBe("light");
    expect(document.cookie).toContain("hd_theme=light");
    expect(icon.getAttribute("href")).toBe("/favicon-light-32.png");

    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.cookie).toContain("hd_theme=dark");
    expect(icon.getAttribute("href")).toBe("/favicon-dark-32.png");
  });

  it("syncFavicon follows the .dark class and leaves other links alone", () => {
    const icon = addIcon("/favicon-light-16.png");
    const apple = document.createElement("link");
    apple.rel = "apple-touch-icon";
    apple.href = "/apple-touch-icon.png";
    document.head.appendChild(apple);

    document.documentElement.classList.add("dark");
    syncFavicon();
    expect(icon.getAttribute("href")).toBe("/favicon-dark-16.png");
    expect(apple.getAttribute("href")).toBe("/apple-touch-icon.png");
  });
});
