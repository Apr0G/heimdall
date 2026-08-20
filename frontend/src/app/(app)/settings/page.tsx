"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  NewPasswordFields,
  passwordErrorText,
  passwordPairSchema,
} from "@/components/password-fields";
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
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";

const schema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password"),
    newPassword: z.string(),
    confirm: z.string(),
  })
  .and(passwordPairSchema)
  .refine((v) => v.currentPassword !== v.newPassword, {
    message: "Choose a password you haven't used here before",
    path: ["newPassword"],
  });
type Values = z.infer<typeof schema>;

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your sign-in details. Accounts are created by your practice
          administrator.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            To change your name or email, contact your administrator.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-[max-content_1fr]">
            <dt className="text-muted-foreground">Name</dt>
            <dd>{user?.full_name || "—"}</dd>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="break-all">{user?.email}</dd>
            <dt className="text-muted-foreground">Role</dt>
            <dd>{user ? humanize(user.role) : "—"}</dd>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
          <CardDescription>
            You&rsquo;ll stay signed in here. Your authenticator app is
            unaffected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChangePasswordForm />
        </CardContent>
      </Card>
    </main>
  );
}

function ChangePasswordForm() {
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const submit = async (values: Values) => {
    setFormError(null);
    setDone(false);
    try {
      await api.post("/api/auth/password/change", {
        current_password: values.currentPassword,
        new_password: values.newPassword,
      });
      reset();
      setDone(true);
    } catch (err) {
      setFormError(
        passwordErrorText(err, "Your current password didn't match."),
      );
    }
  };

  return (
    <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="currentPassword">Current password</Label>
        <Input
          id="currentPassword"
          type="password"
          autoComplete="current-password"
          {...register("currentPassword")}
        />
        {errors.currentPassword && (
          <p className="text-sm text-destructive">
            {errors.currentPassword.message}
          </p>
        )}
      </div>
      <NewPasswordFields
        register={register}
        control={control}
        errors={errors}
      />
      {formError && <p className="text-sm text-destructive">{formError}</p>}
      {done && (
        <p
          role="status"
          className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
        >
          Password updated.
        </p>
      )}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Updating…" : "Update password"}
      </Button>
    </form>
  );
}
