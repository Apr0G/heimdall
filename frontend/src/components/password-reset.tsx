"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  NewPasswordFields,
  passwordErrorText,
  passwordPairSchema,
} from "@/components/password-fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

/**
 * Forgot-password flow for a SIGNED-IN user (Settings): email is fixed, we
 * email a code, they choose a new password. The API revokes every session on a
 * reset, so the caller signs out afterwards.
 */
export function PasswordReset({
  email,
  onDone,
  onCancel,
}: {
  email: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [sent, setSent] = useState(false);
  return (
    <>
      {sent ? (
        <ResetStage
          email={email}
          onDone={onDone}
          onResend={() => setSent(false)}
        />
      ) : (
        <RequestStage email={email} onSent={() => setSent(true)} />
      )}
      <p className="mt-5 text-center text-sm text-muted-foreground">
        <button
          type="button"
          onClick={onCancel}
          className="font-medium text-foreground hover:underline"
        >
          Cancel
        </button>
      </p>
    </>
  );
}

function RequestStage({
  email,
  onSent,
}: {
  email: string;
  onSent: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/auth/password/forgot", { email });
      onSent();
    } catch (err) {
      setError(
        axios.isAxiosError(err) && err.response?.status === 429
          ? "Too many attempts. Please wait a while and try again."
          : "Something went wrong. Please try again.",
      );
      setBusy(false);
    }
  };

  return (
    <>
      <h3 className="text-base font-semibold">Reset your password</h3>
      <p className="mt-1 mb-4 text-sm text-muted-foreground">
        We&rsquo;ll email a one-time code to{" "}
        <span className="font-medium text-foreground">{email}</span>. After you
        set a new password you&rsquo;ll be signed out everywhere and sign in
        again.
      </p>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      <Button onClick={send} disabled={busy}>
        {busy ? "Sending…" : "Email me a code"}
      </Button>
    </>
  );
}

const resetSchema = z
  .object({
    code: z.string().regex(/^\d{6}$/, "Enter the 6-digit code"),
    newPassword: z.string(),
    confirm: z.string(),
  })
  .and(passwordPairSchema);
type ResetValues = z.infer<typeof resetSchema>;

function ResetStage({
  email,
  onDone,
  onResend,
}: {
  email: string;
  onDone: () => void;
  onResend: () => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({ resolver: zodResolver(resetSchema) });

  const submit = async (values: ResetValues) => {
    setFormError(null);
    try {
      await api.post("/api/auth/password/reset", {
        email,
        code: values.code,
        new_password: values.newPassword,
      });
      onDone();
    } catch (err) {
      setFormError(
        passwordErrorText(
          err,
          "That code didn't match, or it expired. Request a new one.",
        ),
      );
    }
  };

  return (
    <>
      <h3 className="text-base font-semibold">Check your email</h3>
      <p className="mt-1 mb-4 text-sm text-muted-foreground">
        Enter the 6-digit code we sent to{" "}
        <span className="font-medium text-foreground">{email}</span> and choose
        a new password.
      </p>
      <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="reset-code">Code</Label>
          <Input
            id="reset-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            placeholder="123456"
            maxLength={6}
            className="max-w-[12rem] text-center font-mono tracking-[0.4em]"
            {...register("code")}
          />
          {errors.code && (
            <p className="text-sm text-destructive">{errors.code.message}</p>
          )}
        </div>
        <NewPasswordFields
          register={register}
          control={control}
          errors={errors}
        />
        {formError && <p className="text-sm text-destructive">{formError}</p>}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Resetting…" : "Reset password"}
        </Button>
      </form>
      <p className="mt-3 text-xs text-muted-foreground">
        Didn&rsquo;t get it?{" "}
        <button
          type="button"
          onClick={onResend}
          className="font-medium text-foreground hover:underline"
        >
          Send a new code
        </button>
      </p>
    </>
  );
}
