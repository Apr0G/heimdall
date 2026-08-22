"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { MailIcon, UserPlusIcon } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type AdminUser,
  type AdminUsers,
  type DeactivationRequestItem,
  fetchAdminUsers,
  fetchDeactivationRequests,
  inviteUser,
  resendInvite,
  resolveDeactivationRequest,
  setUserActive,
} from "@/lib/admin";
import { useAuth } from "@/lib/auth-context";
import { humanize } from "@/lib/format";

const QUERY_KEY = ["admin-users"];
const REQUESTS_KEY = ["admin-deactivation-requests"];
const NEW_PRACTICE = "__new__";
const ROLES = ["doctor", "office_manager", "admin"] as const;

function apiErrorText(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string" && err.response && err.response.status < 500)
      return detail;
  }
  return fallback;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function AdminUsersPage() {
  const [inviting, setInviting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const users = useQuery({ queryKey: QUERY_KEY, queryFn: fetchAdminUsers });

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Users</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Invite staff, re-send invitations, and deactivate accounts.
          </p>
        </div>
        <Button
          variant={inviting ? "outline" : "default"}
          onClick={() => setInviting((v) => !v)}
          aria-expanded={inviting}
          disabled={users.isLoading || users.isError}
        >
          {!inviting && <UserPlusIcon aria-hidden />}
          {inviting ? "Close" : "Invite user"}
        </Button>
      </div>

      {inviting && users.data && (
        <InviteForm
          practices={users.data.practices}
          onDone={(message) => {
            setInviting(false);
            setNotice(message);
          }}
        />
      )}

      {notice && (
        <p
          role="status"
          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
        >
          {notice}
        </p>
      )}

      <DeactivationRequests onNotice={setNotice} />

      {users.isLoading && <Skeleton className="h-64 rounded-lg" />}
      {users.isError && (
        <div className="rounded-md border border-dashed p-10 text-center text-sm text-muted-foreground">
          Couldn&apos;t load users. Refresh to try again.
        </div>
      )}
      {users.data && <UsersTable data={users.data} onNotice={setNotice} />}
    </section>
  );
}

// --- Invite -----------------------------------------------------------------

const inviteSchema = z
  .object({
    email: z.string().email("Enter a valid email"),
    full_name: z.string().max(120).optional(),
    role: z.enum(ROLES),
    practice: z.string().min(1, "Choose a practice"),
    practice_name: z.string().optional(),
  })
  .refine(
    (v) =>
      v.practice !== NEW_PRACTICE || (v.practice_name ?? "").trim().length > 0,
    {
      message: "Name the new practice",
      path: ["practice_name"],
    },
  );
type InviteValues = z.infer<typeof inviteSchema>;

function InviteForm({
  practices,
  onDone,
}: {
  practices: AdminUsers["practices"];
  onDone: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: {
      role: "doctor",
      practice: practices[0]?.id ?? NEW_PRACTICE,
    },
  });
  const practice = useWatch({ control, name: "practice" });

  const submit = async (values: InviteValues) => {
    setFormError(null);
    try {
      const result = await inviteUser({
        email: values.email,
        role: values.role,
        full_name: values.full_name?.trim() || null,
        practice_id: values.practice === NEW_PRACTICE ? null : values.practice,
        practice_name:
          values.practice === NEW_PRACTICE
            ? values.practice_name?.trim()
            : null,
      });
      await queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      onDone(
        result.created_user
          ? `Invitation sent to ${result.user.email}. They'll receive a temporary password by email (valid 7 days).`
          : `${result.user.email} already had an account — a fresh invitation was sent.`,
      );
    } catch (err) {
      setFormError(
        apiErrorText(err, "Couldn't send the invitation. Please try again."),
      );
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Invite a user</CardTitle>
        <CardDescription>
          We create the account and email them a temporary password. On first
          sign-in they choose their own password and set up an authenticator
          app.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={handleSubmit(submit)}
          className="grid gap-4 sm:grid-cols-2"
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="off"
              autoFocus
              {...register("email")}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name (optional)</Label>
            <Input
              id="full_name"
              autoComplete="off"
              placeholder="Dr. Jane Doe"
              {...register("full_name")}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <NativeSelect id="role" {...register("role")}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="practice">Practice</Label>
            <NativeSelect id="practice" {...register("practice")}>
              {practices.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
              <option value={NEW_PRACTICE}>+ New practice…</option>
            </NativeSelect>
            {errors.practice && (
              <p className="text-sm text-destructive">
                {errors.practice.message}
              </p>
            )}
          </div>
          {practice === NEW_PRACTICE && (
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="practice_name">New practice name</Label>
              <Input
                id="practice_name"
                autoComplete="off"
                {...register("practice_name")}
              />
              {errors.practice_name && (
                <p className="text-sm text-destructive">
                  {errors.practice_name.message}
                </p>
              )}
            </div>
          )}
          {formError && (
            <p className="text-sm text-destructive sm:col-span-2">
              {formError}
            </p>
          )}
          <div className="sm:col-span-2">
            <Button type="submit" disabled={isSubmitting}>
              <MailIcon aria-hidden />
              {isSubmitting ? "Sending…" : "Send invitation"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// --- Table ------------------------------------------------------------------

function StatusBadge({ user }: { user: AdminUser }) {
  if (!user.is_active) return <Badge variant="destructive">Deactivated</Badge>;
  if (user.invite_pending)
    return <Badge variant="outline">Invite pending</Badge>;
  return <Badge variant="secondary">Active</Badge>;
}

function UsersTable({
  data,
  onNotice,
}: {
  data: AdminUsers;
  onNotice: (m: string) => void;
}) {
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(
    null,
  );

  const refresh = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const resend = useMutation({
    mutationFn: (id: string) => resendInvite(id),
    onSuccess: (u) => onNotice(`Invitation re-sent to ${u.email}.`),
    onError: (err, id) =>
      setRowError({
        id,
        text: apiErrorText(err, "Couldn't re-send the invitation."),
      }),
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      setUserActive(id, active),
    onSuccess: (u) => {
      setConfirming(null);
      onNotice(
        u.is_active
          ? `${u.email} reactivated.`
          : `${u.email} deactivated and signed out everywhere.`,
      );
      refresh();
    },
    onError: (err, vars) =>
      setRowError({
        id: vars.id,
        text: apiErrorText(err, "Couldn't update the account."),
      }),
  });

  const busy = resend.isPending || toggle.isPending;

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>User</TableHead>
            <TableHead>Practice</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last sign-in</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.users.length === 0 && (
            <TableRow>
              <TableCell
                colSpan={6}
                className="py-10 text-center text-muted-foreground"
              >
                No users yet — invite the first one.
              </TableCell>
            </TableRow>
          )}
          {data.users.map((u) => {
            const isMe = u.id === me?.id;
            const isConfirming = confirming === u.id;
            return (
              <TableRow key={u.id} data-testid={`user-row-${u.email}`}>
                <TableCell>
                  <div className="font-medium">{u.full_name ?? "—"}</div>
                  <div className="text-xs text-muted-foreground">
                    {u.email}
                    {isMe && " (you)"}
                  </div>
                </TableCell>
                <TableCell>{u.practice_name}</TableCell>
                <TableCell>{humanize(u.role)}</TableCell>
                <TableCell>
                  <StatusBadge user={u} />
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatDate(u.last_login_at)}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex flex-wrap items-center justify-end gap-1.5">
                    {u.is_active && u.invite_pending && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => {
                          setRowError(null);
                          resend.mutate(u.id);
                        }}
                      >
                        Resend invite
                      </Button>
                    )}
                    {!isMe && u.is_active && !isConfirming && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => setConfirming(u.id)}
                      >
                        Deactivate
                      </Button>
                    )}
                    {!isMe && u.is_active && isConfirming && (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() => setConfirming(null)}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={busy}
                          onClick={() => {
                            setRowError(null);
                            toggle.mutate({ id: u.id, active: false });
                          }}
                        >
                          Confirm deactivate
                        </Button>
                      </>
                    )}
                    {!isMe && !u.is_active && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => {
                          setRowError(null);
                          toggle.mutate({ id: u.id, active: true });
                        }}
                      >
                        Reactivate
                      </Button>
                    )}
                  </div>
                  {rowError?.id === u.id && (
                    <p className="mt-1 text-xs text-destructive">
                      {rowError.text}
                    </p>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// --- Deactivation requests ------------------------------------------------------

function DeactivationRequests({ onNotice }: { onNotice: (m: string) => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const requests = useQuery({
    queryKey: REQUESTS_KEY,
    queryFn: fetchDeactivationRequests,
  });

  const resolve = useMutation({
    mutationFn: ({
      id,
      decision,
    }: {
      id: string;
      decision: "approve" | "deny";
    }) => resolveDeactivationRequest(id, decision),
    onSuccess: (u, vars) => {
      setError(null);
      onNotice(
        vars.decision === "approve"
          ? `${u.email} deactivated and signed out everywhere.`
          : `Request from ${u.email} denied; their account stays active.`,
      );
      queryClient.invalidateQueries({ queryKey: REQUESTS_KEY });
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
    onError: (err) =>
      setError(apiErrorText(err, "Couldn't resolve the request.")),
  });

  if (!requests.data || requests.data.length === 0) return null;

  return (
    <Card className="border-amber-500/40">
      <CardHeader>
        <CardTitle>Deactivation requests</CardTitle>
        <CardDescription>
          These people asked to have their account deactivated. Approving
          deactivates them immediately; denying leaves the account as is. Either
          way they can see the outcome in their settings.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {requests.data.map((r: DeactivationRequestItem) => (
          <div
            key={r.id}
            data-testid={`deactivation-request-${r.user.email}`}
            className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border p-3"
          >
            <div className="min-w-0 text-sm">
              <div className="font-medium">
                {r.user.full_name ?? r.user.email}
              </div>
              <div className="text-xs text-muted-foreground">
                {r.user.email} · {r.user.practice_name} ·{" "}
                {humanize(r.user.role)} · {formatDate(r.created_at)}
              </div>
              <p className="mt-1.5 text-muted-foreground">
                {r.reason ? (
                  <>&ldquo;{r.reason}&rdquo;</>
                ) : (
                  <em>No reason given</em>
                )}
              </p>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <Button
                size="sm"
                variant="outline"
                disabled={resolve.isPending}
                onClick={() => resolve.mutate({ id: r.id, decision: "deny" })}
              >
                Deny
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={resolve.isPending}
                onClick={() =>
                  resolve.mutate({ id: r.id, decision: "approve" })
                }
              >
                Approve & deactivate
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
