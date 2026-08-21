"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

/**
 * Lost / change authenticator. Two proofs: the account password, then a code we
 * email. On success the old authenticator is gone and every session is signed
 * out; the next sign-in walks through enrollment again. Used from the login page
 * (email editable) and from Settings (email fixed to the signed-in user).
 */
export function AuthenticatorRecovery({
  email,
  onDone,
  onCancel,
  cancelLabel = "Back",
}: {
  email?: string;
  onDone: () => void;
  onCancel: () => void;
  cancelLabel?: string;
}) {
  const [stage, setStage] = useState<
    { name: "password" } | { name: "code"; email: string; password: string }
  >({
    name: "password",
  });

  return (
    <>
      {stage.name === "password" && (
        <PasswordStage
          email={email}
          onSent={(e, p) => setStage({ name: "code", email: e, password: p })}
        />
      )}
      {stage.name === "code" && (
        <CodeStage
          email={stage.email}
          password={stage.password}
          onDone={onDone}
          onResend={() => setStage({ name: "password" })}
        />
      )}
      <p className="mt-5 text-center text-sm text-muted-foreground">
        <button
          type="button"
          onClick={onCancel}
          className="font-medium text-foreground hover:underline"
        >
          {cancelLabel}
        </button>
      </p>
    </>
  );
}

function errorText(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    if (status === 401) return fallback;
    if (status === 400 && typeof detail === "string") return detail;
    if (status === 429)
      return "Too many attempts. Please wait a while and try again.";
    if (
      status === 502 &&
      typeof detail === "string" &&
      detail.includes("email")
    )
      return detail;
  }
  return "Something went wrong. Please try again.";
}

const passwordSchema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
});
type PasswordValues = z.infer<typeof passwordSchema>;

function PasswordStage({
  email,
  onSent,
}: {
  email?: string;
  onSent: (email: string, password: string) => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { email: email ?? "" },
  });

  const submit = async (values: PasswordValues) => {
    setFormError(null);
    try {
      await api.post("/api/auth/mfa/recover/start", {
        email: values.email,
        password: values.password,
      });
      onSent(values.email, values.password);
    } catch (err) {
      setFormError(
        errorText(err, "That email or password doesn't match our records."),
      );
    }
  };

  return (
    <>
      <h1 className="text-center text-base font-semibold">
        Reset your authenticator
      </h1>
      <p className="mt-2 mb-6 text-center text-sm text-muted-foreground">
        Confirm your password and we&rsquo;ll email you a one-time code.
        Afterwards you&rsquo;ll set up a new authenticator app the next time you
        sign in.
      </p>
      <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="recover-email">Email</Label>
          <Input
            id="recover-email"
            type="email"
            autoComplete="email"
            readOnly={email !== undefined}
            autoFocus={email === undefined}
            className={
              email !== undefined ? "text-muted-foreground" : undefined
            }
            {...register("email")}
          />
          {errors.email && (
            <p className="text-sm text-destructive">{errors.email.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="recover-password">Password</Label>
          <Input
            id="recover-password"
            type="password"
            autoComplete="current-password"
            autoFocus={email !== undefined}
            {...register("password")}
          />
          {errors.password && (
            <p className="text-sm text-destructive">
              {errors.password.message}
            </p>
          )}
        </div>
        {formError && <p className="text-sm text-destructive">{formError}</p>}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Sending…" : "Email me a code"}
        </Button>
      </form>
    </>
  );
}

function CodeStage({
  email,
  password,
  onDone,
  onResend,
}: {
  email: string;
  password: string;
  onDone: () => void;
  onResend: () => void;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.post("/api/auth/mfa/recover/complete", {
        email,
        password,
        code,
      });
      onDone();
    } catch (err) {
      setError(
        errorText(
          err,
          "That code didn't match, or it expired. Request a new one.",
        ),
      );
      setBusy(false);
    }
  };

  return (
    <>
      <h1 className="text-center text-base font-semibold">Check your email</h1>
      <p className="mt-2 mb-6 text-center text-sm text-muted-foreground">
        We sent a 6-digit code to{" "}
        <span className="font-medium text-foreground">{email}</span>. It expires
        in 10 minutes.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="recover-code">Code</Label>
          <Input
            id="recover-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            placeholder="123456"
            value={code}
            onChange={(e) =>
              setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            className="text-center font-mono tracking-[0.4em]"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button
          type="submit"
          className="w-full"
          disabled={busy || code.length < 6}
        >
          {busy ? "Resetting…" : "Reset authenticator"}
        </Button>
      </form>
      <p className="mt-3 text-center text-xs text-muted-foreground">
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
