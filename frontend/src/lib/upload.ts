import axios from "axios";

import { api } from "@/lib/api";

export type DocType = "denial" | "claim" | "clinical";
export const DOC_TYPES: DocType[] = ["denial", "claim", "clinical"];

type PresignedSlot = { doc_type: DocType; s3_key: string; upload_url: string };

/**
 * Presign three uploads, PUT each PDF directly to S3 (with progress), then
 * create the case. Returns the new case id + status.
 */
export async function createCaseWithUploads(
  files: Record<DocType, File>,
  onProgress: (doc: DocType, pct: number) => void,
): Promise<{ id: string; status: string }> {
  const { data: presigned } = await api.post<{ uploads: PresignedSlot[] }>(
    "/api/cases/upload-urls",
    {
      documents: DOC_TYPES.map((doc) => ({
        doc_type: doc,
        filename: files[doc].name,
        content_type: "application/pdf",
      })),
    },
  );

  const keyByDoc = {} as Record<DocType, string>;
  await Promise.all(
    presigned.uploads.map(async (slot) => {
      keyByDoc[slot.doc_type] = slot.s3_key;
      await axios.put(slot.upload_url, files[slot.doc_type], {
        headers: { "Content-Type": "application/pdf" },
        onUploadProgress: (event) => {
          if (event.total) {
            onProgress(slot.doc_type, Math.round((event.loaded / event.total) * 100));
          }
        },
      });
    }),
  );

  const { data } = await api.post<{ id: string; status: string }>("/api/cases", {
    documents: DOC_TYPES.map((doc) => ({
      doc_type: doc,
      s3_key: keyByDoc[doc],
      filename: files[doc].name,
    })),
  });
  return data;
}
