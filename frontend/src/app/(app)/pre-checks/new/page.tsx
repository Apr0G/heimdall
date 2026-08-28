"use client";

import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { FileDrop, type SlotStatus } from "@/components/file-drop";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  createPreCheckWithUploads,
  PRECHECK_DOC_TYPES,
  type PreCheckDocType,
} from "@/lib/upload";

const SLOTS: {
  doc: PreCheckDocType;
  label: string;
  hint: string;
  example: string;
}[] = [
  {
    doc: "claim",
    label: "Draft claim",
    hint: "The CMS-1500 you're about to submit — before it goes to the payer",
    example:
      "The claim form as you intend to bill it, with the CPT, ICD-10, modifier, and unit fields filled in.",
  },
  {
    doc: "clinical",
    label: "Clinical notes",
    hint: "Chart notes, op report, or other documentation for the encounter",
    example:
      "The documentation that has to support the billed codes — SOAP notes, op or imaging reports.",
  },
];

type ByDoc<T> = Record<PreCheckDocType, T>;

const initial = <T,>(value: T): ByDoc<T> => ({ claim: value, clinical: value });

export default function NewPreCheckPage() {
  const router = useRouter();
  const [files, setFiles] = useState<ByDoc<File | null>>(
    initial<File | null>(null),
  );
  const [errors, setErrors] = useState<ByDoc<string | null>>(
    initial<string | null>(null),
  );
  const [status, setStatus] = useState<ByDoc<SlotStatus>>(
    initial<SlotStatus>("idle"),
  );
  const [progress, setProgress] = useState<ByDoc<number>>(initial(0));
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const allSelected = PRECHECK_DOC_TYPES.every((doc) => files[doc] !== null);

  function selectFile(
    doc: PreCheckDocType,
    file: File | null,
    error: string | null,
  ) {
    setFiles((prev) => ({ ...prev, [doc]: file }));
    setErrors((prev) => ({ ...prev, [doc]: error }));
    setStatus((prev) => ({ ...prev, [doc]: "idle" }));
    setProgress((prev) => ({ ...prev, [doc]: 0 }));
  }

  async function onSubmit() {
    if (!allSelected || submitting) return;
    setSubmitting(true);
    setFormError(null);
    setStatus(initial<SlotStatus>("uploading"));
    try {
      const created = await createPreCheckWithUploads(
        files as ByDoc<File>,
        (doc, pct) => {
          setProgress((prev) => ({ ...prev, [doc]: pct }));
          if (pct >= 100) setStatus((prev) => ({ ...prev, [doc]: "done" }));
        },
      );
      // Land on the report page, which polls until the pipeline finishes.
      router.push(`/pre-checks/${created.id}`);
    } catch (err) {
      setStatus(initial<SlotStatus>("error"));
      const message =
        axios.isAxiosError(err) && err.response?.status === 401
          ? "Your session expired. Please sign in again."
          : "Upload failed. Please try again.";
      setFormError(message);
      toast.error(message);
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link
        href="/pre-checks"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <span aria-hidden>←</span> Pre-checks
      </Link>
      <div>
        <h1 className="text-[22px] font-extrabold tracking-tight">
          New pre-check
        </h1>
        <p className="text-sm text-muted-foreground">
          Check a claim before you submit it. Upload the draft claim and the
          clinical notes — Heimdall flags likely denials. PDF only.
        </p>
        <p
          className="mt-3 rounded-md bg-muted p-3 text-xs leading-relaxed text-muted-foreground"
          style={{ borderLeft: "2px solid var(--warn)" }}
        >
          <span className="font-medium text-foreground">
            Want a corrected claim back?
          </span>{" "}
          Export the draft claim from your billing software as a PDF. A scanned
          or photographed claim can still be checked, but Heimdall can&rsquo;t
          edit it for you — you&rsquo;ll get the list of changes to apply
          yourself.
        </p>
      </div>
      <Card>
        <CardContent className="space-y-6 pt-6">
          {SLOTS.map((slot) => (
            <FileDrop
              key={slot.doc}
              label={slot.label}
              hint={slot.hint}
              example={slot.example}
              file={files[slot.doc]}
              status={status[slot.doc]}
              progress={progress[slot.doc]}
              error={errors[slot.doc]}
              onSelect={(file, error) => selectFile(slot.doc, file, error)}
            />
          ))}
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <Button
            className="w-full"
            disabled={!allSelected || submitting}
            onClick={onSubmit}
          >
            {submitting ? "Uploading…" : "Run pre-check"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
