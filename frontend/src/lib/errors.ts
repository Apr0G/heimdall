import axios from "axios";
import { toast } from "sonner";

// The pipeline stores a deliberately terse, PHI-free error_message shaped like
// "Processing failed (ExceptionType[: AWSCode])." We NEVER render that raw — a
// future backend change could interpolate parser/document text into it. Instead
// map the exception-type signals we know about to friendly copy, and fall back
// to a generic message for everything else.
const _PIPELINE_ERROR_COPY: { match: string; text: string }[] = [
  {
    match: "NoBillableLinesError",
    text: "We couldn't read any billable lines from the claim document. Check that the right file was uploaded — it should be the draft CMS-1500 with the CPT and diagnosis codes filled in.",
  },
  {
    match: "DocumentTamperedError",
    text: "A document didn't match its recorded fingerprint and couldn't be processed safely. Re-upload the file and try again.",
  },
  {
    match: "DocumentParseError",
    text: "We couldn't read one of the uploaded PDFs. Make sure each file is a valid, non-corrupt PDF and try again.",
  },
  {
    match: "NotAPdfError",
    text: "One of the uploaded files isn't a PDF. Upload PDF documents only.",
  },
  {
    match: "TooManyPagesError",
    text: "A document has too many pages to process. Split it into smaller PDFs and try again.",
  },
];

// Machine-readable HTTPException details — the API sends these where the
// client has to react, not just display. Any other string detail is already
// user copy.
const _DETAIL_COPY = new Map<string, string>([
  // 409 from POST …/corrected-claim: the report the picks index into is no
  // longer the latest one.
  ["report_changed", "This report changed — reload and pick your edits again"],
]);

const _GENERIC_PIPELINE_ERROR =
  "Something went wrong while processing your documents. Your files are safe — nothing was lost. Try again, and if it keeps happening, email us.";

/** Map the backend's PHI-free pipeline error_message to friendly copy. Returns
 *  a generic message for anything unrecognized, so the raw string never reaches
 *  the screen. */
export function pipelineErrorMessage(raw: string | null | undefined): string {
  if (raw) {
    for (const { match, text } of _PIPELINE_ERROR_COPY) {
      if (raw.includes(match)) return text;
    }
  }
  return _GENERIC_PIPELINE_ERROR;
}

/** Turn any thrown error into a user-friendly toast (never a raw dump). */
export function toastError(
  err: unknown,
  fallback = "Something went wrong. Please try again.",
) {
  let message = fallback;
  if (axios.isAxiosError(err)) {
    if (err.response?.status === 401) {
      message = "Your session expired. Please sign in again.";
    } else if (typeof err.response?.data?.detail === "string") {
      // FastAPI HTTPException detail is already user-facing and PHI-free.
      const detail: string = err.response.data.detail;
      message = _DETAIL_COPY.get(detail) ?? detail;
    }
  }
  toast.error(message);
}
