import axios from "axios";
import { toast } from "sonner";

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
      message = err.response.data.detail;
    }
  }
  toast.error(message);
}
