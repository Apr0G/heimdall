"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

type MyRequest = {
  id: string;
  status: string;
  reason: string | null;
  created_at: string;
} | null;

const QUERY_KEY = ["my-deactivation-request"];

/**
 * Settings card body: ask an admin to deactivate this account. Accounts belong
 * to the practice, so the user can only request; an admin approves or denies.
 * Shows the pending state (with cancel) while a request is open.
 */
export function DeactivationRequestCard() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mine = useQuery({
    queryKey: QUERY_KEY,
    queryFn: async () =>
      (await api.get<MyRequest>("/api/auth/deactivation-request")).data,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const submit = useMutation({
    mutationFn: () =>
      api.post("/api/auth/deactivation-request", {
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      setOpen(false);
      setReason("");
      setError(null);
      refresh();
    },
    onError: (err) =>
      setError(
        axios.isAxiosError(err) && err.response?.status === 409
          ? "You already have a pending request."
          : "Something went wrong. Please try again.",
      ),
  });
  const cancel = useMutation({
    mutationFn: () => api.delete("/api/auth/deactivation-request"),
    onSuccess: refresh,
    onError: () => setError("Couldn't cancel the request. Please try again."),
  });

  if (mine.isLoading) return null;

  if (mine.data) {
    return (
      <div className="space-y-3">
        <p
          role="status"
          className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-300"
        >
          Request sent on{" "}
          {new Date(mine.data.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          })}
          . Your administrator will review it; you can keep using Heimdall until
          then.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          variant="outline"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          {cancel.isPending ? "Cancelling…" : "Cancel request"}
        </Button>
      </div>
    );
  }

  if (!open) {
    return (
      <Button variant="destructive" onClick={() => setOpen(true)}>
        Request deactivation
      </Button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit.mutate();
      }}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="deactivation-reason">Reason (optional)</Label>
        <Textarea
          id="deactivation-reason"
          rows={3}
          maxLength={500}
          autoFocus
          placeholder="e.g. Leaving the practice at the end of the month"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      <p className="text-sm text-muted-foreground">
        Once approved you&rsquo;ll lose access immediately. Your records stay
        with the practice.
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" variant="destructive" disabled={submit.isPending}>
          {submit.isPending ? "Sending…" : "Send request"}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
