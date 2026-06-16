"use client";

import { useRef, useState } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type SlotStatus = "idle" | "uploading" | "done" | "error";

export function FileDrop({
  label,
  hint,
  example,
  file,
  status,
  progress,
  error,
  onSelect,
}: {
  label: string;
  hint: string;
  example: string;
  file: File | null;
  status: SlotStatus;
  progress: number;
  error: string | null;
  onSelect: (file: File | null, error: string | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handle(files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      onSelect(null, "Only PDF files are accepted.");
      return;
    }
    onSelect(f, null);
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span className="text-sm font-medium">{label}</span>
        <Tooltip>
          <TooltipTrigger className="inline-flex size-4 items-center justify-center rounded-full border text-[10px] text-muted-foreground">
            ?
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{example}</TooltipContent>
        </Tooltip>
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => handle(e.target.files)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handle(e.dataTransfer.files);
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed p-6 text-center transition-colors",
          dragging ? "border-primary bg-muted/50" : "border-input hover:bg-muted/30",
          status === "error" && "border-destructive",
        )}
      >
        {file ? (
          <span className="text-sm font-medium break-all">{file.name}</span>
        ) : (
          <span className="text-sm text-muted-foreground">
            Drag a PDF here, or click to browse
          </span>
        )}
        {status === "uploading" && (
          <span className="text-xs text-muted-foreground">Uploading… {progress}%</span>
        )}
        {status === "done" && <span className="text-xs text-emerald-600">Uploaded ✓</span>}
      </button>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
