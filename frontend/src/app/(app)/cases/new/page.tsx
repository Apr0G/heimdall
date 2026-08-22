"use client";

import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { FileDrop, type SlotStatus } from "@/components/file-drop";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { createCaseWithUploads, DOC_TYPES, type DocType } from "@/lib/upload";

const SLOTS: { doc: DocType; label: string; hint: string; example: string }[] =
  [
    {
      doc: "denial",
      label: "Denial document",
      hint: "EOB, ERA, or denial letter from the insurance company",
      example:
        "The payer's response showing the CARC/RARC denial codes and the denied amount.",
    },
    {
      doc: "claim",
      label: "Original claim",
      hint: "The CMS-1500 or UB-04 form you submitted",
      example:
        "The claim form you billed, with the CPT, ICD-10, and modifier codes.",
    },
    {
      doc: "clinical",
      label: "Clinical notes",
      hint: "Chart notes, op report, or other clinical documentation",
      example:
        "Documentation supporting medical necessity — SOAP notes, op or imaging reports.",
    },
  ];

type ByDoc<T> = Record<DocType, T>;

const initial = <T,>(value: T): ByDoc<T> => ({
  denial: value,
  claim: value,
  clinical: value,
});

export default function NewCasePage() {
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

  const allSelected = DOC_TYPES.every((doc) => files[doc] !== null);

  function selectFile(doc: DocType, file: File | null, error: string | null) {
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
      const created = await createCaseWithUploads(
        files as ByDoc<File>,
        (doc, pct) => {
          setProgress((prev) => ({ ...prev, [doc]: pct }));
          if (pct >= 100) setStatus((prev) => ({ ...prev, [doc]: "done" }));
        },
      );
      // Land on the case detail page, which polls until the pipeline finishes.
      router.push(`/cases/${created.id}`);
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
        href="/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <span aria-hidden>←</span> Appeals
      </Link>
      <div>
        <h1 className="text-[22px] font-extrabold tracking-tight">
          New appeal
        </h1>
        <p className="text-sm text-muted-foreground">
          Upload three documents. Heimdall handles the rest. PDF only.
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
            {submitting ? "Uploading…" : "Create appeal"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
