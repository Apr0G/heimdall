"use client";

import { useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { type DocumentDetail, fetchDocumentDownloadUrl } from "@/lib/cases";
import { toastError } from "@/lib/errors";
import { humanize } from "@/lib/format";
import { CONTACT_MAILTO } from "@/lib/site";

// Shared across the appeal and pre-check detail pages (extracted from
// cases/[id]/page.tsx unchanged; ProcessingView's copy became props so the
// pre-check page can describe its own pipeline steps).

export const DOC_LABELS: Record<string, string> = {
  denial: "Denial document",
  claim: "Original claim",
  clinical: "Clinical notes",
  prior_auth: "Prior authorization",
  prior_treatment: "Prior treatment records",
};

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-medium">{children}</div>
    </div>
  );
}

export type ProcessingStep = { label: string; token: string };

export function ProcessingView({
  stalled,
  pollFailed = false,
  onRetry,
  retrying,
  title,
  description,
  steps,
}: {
  stalled: boolean;
  pollFailed?: boolean;
  onRetry: () => void;
  retrying: boolean;
  title: string;
  description: string;
  steps: ProcessingStep[];
}) {
  // The pipeline runs in-process, so a deploy/crash can strand a case in
  // `processing`. Once the server flags it stalled — or once we can no longer
  // reach the status endpoint at all — offer a way out rather than spinning.
  if (stalled || pollFailed) {
    return (
      <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
        <span
          className="mb-5 flex size-[52px] items-center justify-center rounded-full text-2xl font-bold"
          style={{
            background: "color-mix(in oklab, var(--warn) 16%, var(--card))",
            color: "var(--warn)",
          }}
          aria-hidden
        >
          ⏱
        </span>
        <div className="mb-2 text-xl font-extrabold tracking-tight">
          This is taking longer than expected
        </div>
        <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
          Your documents are safe — nothing was lost. The analysis didn&rsquo;t
          finish, which can happen after a system update. Retry to pick it back
          up.
        </p>
        <div className="mt-6 flex gap-2.5">
          <Button onClick={onRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry"}
          </Button>
          <a
            href={CONTACT_MAILTO}
            className={buttonVariants({ variant: "outline" })}
          >
            Contact support
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
      <span className="mb-6 size-11 animate-spin rounded-full border-[3px] border-border border-t-primary" />
      <div className="mb-2 text-xl font-extrabold tracking-tight">{title}</div>
      <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
        {description}
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3 text-[12.5px]">
        {steps.map((step) => (
          // Inline var() styles, not `text-${token}` utilities — dynamic class
          // names are invisible to the Tailwind compiler and silently unstyled.
          <span
            key={step.label}
            className="inline-flex items-center gap-1.5"
            style={{ color: `var(${step.token})` }}
          >
            <span
              className="size-1.5 rounded-full"
              style={{ background: `var(${step.token})` }}
              aria-hidden
            />
            {step.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ErrorView({
  message,
  onRetry,
  retrying,
}: {
  message: string | null;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-border bg-card px-6 py-24 text-center shadow-sm">
      <span
        className="mb-5 flex size-[52px] items-center justify-center rounded-full text-2xl font-bold"
        style={{
          background: "color-mix(in oklab, var(--danger) 16%, var(--card))",
          color: "var(--danger)",
        }}
        aria-hidden
      >
        !
      </span>
      <div className="mb-2 text-xl font-extrabold tracking-tight">
        We couldn&rsquo;t finish this analysis
      </div>
      <p className="max-w-md text-[15px] leading-relaxed text-muted-foreground">
        {message ??
          "Something went wrong while reading your documents. Your files are safe — nothing was lost. Try again, and if it keeps happening, email us."}
      </p>
      <div className="mt-6 flex gap-2.5">
        <Button onClick={onRetry} disabled={retrying}>
          {retrying ? "Retrying…" : "Retry"}
        </Button>
        <a
          href={CONTACT_MAILTO}
          className={buttonVariants({ variant: "outline" })}
        >
          Contact support
        </a>
      </div>
    </div>
  );
}

export function DocumentsCard({ documents }: { documents: DocumentDetail[] }) {
  const [opening, setOpening] = useState<string | null>(null);

  async function open(docId: string) {
    setOpening(docId);
    try {
      const url = await fetchDocumentDownloadUrl(docId);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toastError(e, "Couldn't open the document.");
    } finally {
      setOpening(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
      </CardHeader>
      <CardContent className="divide-y">
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No documents.</p>
        ) : (
          documents.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between py-2 first:pt-0 last:pb-0"
            >
              <div>
                <div className="text-sm font-medium">
                  {DOC_LABELS[d.doc_type] ?? humanize(d.doc_type)}
                </div>
                <div className="text-xs text-muted-foreground">
                  {d.original_filename ?? "document.pdf"}
                  {d.text_source === "form_fields" && (
                    <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[11px] text-foreground">
                      Fillable form
                    </span>
                  )}
                  {d.text_source === "ocr" && (
                    <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-[11px]">
                      Scanned
                    </span>
                  )}
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => open(d.id)}
                disabled={opening === d.id}
              >
                {opening === d.id ? "Opening…" : "View"}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
