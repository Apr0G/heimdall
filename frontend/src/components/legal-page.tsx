import Link from "next/link";

/**
 * Shared shell for the legal pages (Terms, Privacy, Subprocessors). Renders the
 * title, the effective / last-updated line, a small nav between the three
 * documents, and prose styling for the nested headings, lists and tables the
 * generated bodies use (no typography plugin needed). The bodies themselves
 * are generated from docs/policies/*.md, which is the retained policy record.
 */
const LEGAL_PAGES = [
  { href: "/terms", label: "Terms of Service" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/subprocessors", label: "Subprocessors" },
];

export function LegalPage({
  title,
  effective,
  lastUpdated,
  children,
}: {
  title: string;
  effective: string;
  lastUpdated: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Effective {effective} &middot; Last updated {lastUpdated}
      </p>
      <nav
        aria-label="Legal documents"
        className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground"
      >
        {LEGAL_PAGES.map((page) => (
          <Link
            key={page.href}
            href={page.href}
            className="underline-offset-4 hover:text-foreground hover:underline"
          >
            {page.label}
          </Link>
        ))}
      </nav>
      <div className="mt-8 space-y-4 text-sm leading-relaxed text-muted-foreground [&_a]:underline [&_a]:underline-offset-4 [&_a:hover]:text-foreground [&_h2]:mt-10 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-foreground [&_h3]:mt-6 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-foreground [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_strong]:font-medium [&_strong]:text-foreground [&_table]:w-full [&_table]:border-collapse [&_table]:text-left [&_table]:text-xs [&_td]:py-2 [&_td]:pr-3 [&_td]:align-top [&_th]:py-2 [&_th]:pr-3 [&_th]:font-semibold [&_th]:text-foreground [&_tr]:border-b [&_tr]:border-border [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}
