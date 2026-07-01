/**
 * Shared shell for the Terms / Privacy pages. Renders a title, a "last updated"
 * line, a clear placeholder banner, and prose styling for nested <h2>/<p>/<ul>
 * (no typography plugin needed).
 */
export function LegalPage({
  title,
  lastUpdated,
  children,
}: {
  title: string;
  lastUpdated: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated: {lastUpdated}</p>
      <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        Placeholder template for the MVP — this is not legal advice, and the final text will be
        reviewed by counsel before launch.
      </div>
      <div className="mt-8 space-y-4 text-sm leading-relaxed text-muted-foreground [&_h2]:mt-8 [&_h2]:text-base [&_h2]:font-medium [&_h2]:text-foreground [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}
