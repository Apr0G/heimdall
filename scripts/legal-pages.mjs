// Regenerates the public legal pages from their Markdown sources.
//
//   node scripts/legal-pages.mjs          (from the repo root)
//
// docs/policies/*.md is the retained policy record (HIPAA 164.316(b)(2)(i) wants
// six years of policy history, and git gives us that for free); the Next pages
// under frontend/src/app/(marketing)/ are a rendering of it. Edit the Markdown,
// run this, then `npx prettier --write` on the output. The Markdown subset
// understood here: "# " title (ignored; the title is in PAGES), one
// "Effective: X. Last updated: Y." line, "## " / "### " headings, paragraphs,
// "- " and "1. " lists, pipe tables with a --- separator row, **bold**, and
// [text](href) links. A mailto link to CONTACT_EMAIL is rendered from the
// constant so the address lives in one place.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const CONTACT = "info@heimdallclaims.com";

const PAGES = [
  {
    source: "docs/policies/terms-of-service.md",
    target: "frontend/src/app/(marketing)/terms/page.tsx",
    component: "TermsPage",
    title: "Terms of Service",
    description: "The terms that govern use of the Heimdall Claims website and service.",
  },
  {
    source: "docs/policies/privacy-policy.md",
    target: "frontend/src/app/(marketing)/privacy/page.tsx",
    component: "PrivacyPage",
    title: "Privacy Policy",
    description: "How Heimdall Claims collects, uses, shares and protects information.",
  },
  {
    source: "docs/policies/subprocessors.md",
    target: "frontend/src/app/(marketing)/subprocessors/page.tsx",
    component: "SubprocessorsPage",
    title: "Subprocessors",
    description: "The third-party service providers Heimdall Claims uses and what each one receives.",
  },
];

function esc(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\{/g, "&#123;")
    .replace(/\}/g, "&#125;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function slug(s) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

function render(page) {
  const used = { link: false, contact: false };

  function inline(raw) {
    let out = "";
    const re = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;
    let last = 0;
    let m;
    while ((m = re.exec(raw)) !== null) {
      out += esc(raw.slice(last, m.index));
      if (m[1] !== undefined) {
        const [, text, href] = m;
        if (href === `mailto:${CONTACT}` && text === CONTACT) {
          used.contact = true;
          out += "<a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>";
        } else if (href.startsWith("/")) {
          used.link = true;
          out += `<Link href="${href}">${esc(text)}</Link>`;
        } else {
          out += `<a href="${href}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`;
        }
      } else {
        out += `<strong>${esc(m[3])}</strong>`;
      }
      last = re.lastIndex;
    }
    return out + esc(raw.slice(last));
  }

  const lines = readFileSync(join(ROOT, page.source), "utf8").replace(/\r\n/g, "\n").split("\n");
  const body = [];
  let para = [];
  let list = null;
  let table = null;
  let effective = "";
  let lastUpdated = "";

  const flushPara = () => {
    if (para.length) body.push(`<p>${inline(para.join(" "))}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list) body.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join("")}</${list.tag}>`);
    list = null;
  };
  const flushTable = () => {
    if (table) {
      const th = table.header.map((h) => `<th scope="col">${inline(h)}</th>`).join("");
      const rows = table.rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("");
      body.push(`<table><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table>`);
    }
    table = null;
  };
  const flushAll = () => { flushPara(); flushList(); flushTable(); };

  for (const line of lines) {
    const t = line.trimEnd();
    if (t.startsWith("# ")) continue;
    const meta = t.match(/^Effective: (.+?)\. Last updated: (.+?)\.$/);
    if (meta) { [, effective, lastUpdated] = meta; continue; }
    if (t === "") { flushAll(); continue; }
    if (t.startsWith("## ")) { flushAll(); const h = t.slice(3); body.push(`<h2 id="${slug(h)}">${inline(h)}</h2>`); continue; }
    if (t.startsWith("### ")) { flushAll(); const h = t.slice(4); body.push(`<h3 id="${slug(h)}">${inline(h)}</h3>`); continue; }
    if (t.startsWith("|")) {
      flushPara(); flushList();
      const cells = t.slice(1, t.endsWith("|") ? -1 : undefined).split("|").map((c) => c.trim());
      if (cells.every((c) => /^-{3,}$/.test(c))) continue;
      if (table) table.rows.push(cells); else table = { header: cells, rows: [] };
      continue;
    }
    const li = t.match(/^- (.*)$/) || t.match(/^\d+\. (.*)$/);
    if (li) {
      flushPara(); flushTable();
      const tag = t.startsWith("-") ? "ul" : "ol";
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push(li[1]);
      continue;
    }
    flushList(); flushTable();
    para.push(t.trim());
  }
  flushAll();
  if (!effective || !lastUpdated) throw new Error(`${page.source}: missing the "Effective: X. Last updated: Y." line`);

  const imports = [
    'import type { Metadata } from "next";',
    used.link ? 'import Link from "next/link";' : null,
    "",
    'import { LegalPage } from "@/components/legal-page";',
    used.contact ? 'import { CONTACT_EMAIL } from "@/lib/site";' : null,
  ].filter((l) => l !== null).join("\n");

  return `// GENERATED from ${page.source} by scripts/legal-pages.mjs. Do not hand-edit the
// body: edit the Markdown (the retained policy record) and regenerate.
${imports}

export const metadata: Metadata = {
  description: ${JSON.stringify(page.description)},
};

export default function ${page.component}() {
  return (
    <LegalPage title=${JSON.stringify(page.title)} effective=${JSON.stringify(effective)} lastUpdated=${JSON.stringify(lastUpdated)}>
      ${body.join("\n      ")}
    </LegalPage>
  );
}
`;
}

for (const page of PAGES) {
  writeFileSync(join(ROOT, page.target), render(page), "utf8");
  console.log(`${page.target} <- ${page.source}`);
}