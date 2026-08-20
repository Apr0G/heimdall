"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { MarketingHeader } from "@/components/marketing-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth-context";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

// Mirrors the Cognito pool's password_policy in main.tf. Cognito is the enforcer;
// this just gives the user the rules up front instead of after a round-trip.
const PASSWORD_RULES = [
  { label: "At least 12 characters", test: (p: string) => p.length >= 12 },
  { label: "An uppercase letter", test: (p: string) => /[A-Z]/.test(p) },
  { label: "A lowercase letter", test: (p: string) => /[a-z]/.test(p) },
  { label: "A number", test: (p: string) => /\d/.test(p) },
  { label: "A symbol", test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

const newPasswordSchema = z
  .object({
    newPassword: z
      .string()
      .refine(
        (p) => PASSWORD_RULES.every((r) => r.test(p)),
        "Password doesn't meet the rules below",
      ),
    confirm: z.string(),
  })
  .refine((v) => v.newPassword === v.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });

type NewPasswordValues = z.infer<typeof newPasswordSchema>;

// After a correct password, Cognito may require a new password (first login with a
// temporary one), a TOTP code (enrolled), or a first-time enrollment (MFA_SETUP).
// We carry the email + Cognito session through; new_password chains into the
// MFA steps the same way the password step does.
type Step =
  | { name: "password" }
  | { name: "new_password"; email: string; session: string }
  | { name: "code"; email: string; session: string }
  | { name: "setup"; email: string; session: string; secret: string };

const GLOW = {
  backgroundImage:
    "radial-gradient(90% 60% at 50% 0%, color-mix(in oklab, var(--color-amber-500) 12%, transparent), transparent 60%)",
};

function errorText(err: unknown): string {
  if (
    axios.isAxiosError(err) &&
    (err.response?.status === 401 || err.response?.status === 400)
  ) {
    return "That code didn't match, or it expired. Try again.";
  }
  return "Something went wrong. Please try again.";
}

export default function LoginPage() {
  const { login, verifyMfa, startMfaSetup, completeMfaSetup, setNewPassword } =
    useAuth();
  const [step, setStep] = useState<Step>({ name: "password" });

  const onChallenge = async (
    email: string,
    challenge: string,
    session: string,
  ) => {
    if (challenge === "NEW_PASSWORD_REQUIRED") {
      setStep({ name: "new_password", email, session });
    } else if (challenge === "MFA_SETUP") {
      const s = await startMfaSetup(email, session);
      setStep({ name: "setup", email, session: s.session, secret: s.secret });
    } else {
      setStep({ name: "code", email, session });
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* Brand bar + header so visitors can click the logo back to the landing page. */}
      <div className="h-1 bg-gradient-to-r from-amber-500 to-blue-500" />
      <MarketingHeader showLogin={false} />
      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        <div
          aria-hidden
          style={GLOW}
          className="pointer-events-none absolute inset-0"
        />
        <div className="relative w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-md">
          {step.name === "password" && (
            <PasswordStep onLogin={login} onChallenge={onChallenge} />
          )}

          {step.name === "new_password" && (
            <NewPasswordStep
              onSubmit={(pw) => setNewPassword(step.email, step.session, pw)}
              onChallenge={(challenge, session) =>
                onChallenge(step.email, challenge, session)
              }
            />
          )}

          {step.name === "code" && (
            <CodeStep
              title="Two-factor authentication"
              description="Enter the 6-digit code from your authenticator app."
              onSubmit={(code) => verifyMfa(step.email, step.session, code)}
            />
          )}

          {step.name === "setup" && (
            <CodeStep
              title="Set up two-factor authentication"
              description="Scan this QR code with an authenticator app (Google Authenticator, Authy, 1Password), then enter the 6-digit code it shows."
              onSubmit={(code) =>
                completeMfaSetup(step.email, step.session, code)
              }
            >
              <div className="flex justify-center">
                <div className="rounded-md bg-white p-3">
                  <QRCodeSVG
                    value={`otpauth://totp/Heimdall:${encodeURIComponent(step.email)}?secret=${step.secret}&issuer=Heimdall`}
                    size={160}
                    bgColor="#ffffff"
                    fgColor="#000000"
                  />
                </div>
              </div>
              <p className="text-center text-xs text-muted-foreground">
                Can&rsquo;t scan? Enter this key manually:
                <br />
                <span className="font-mono break-all text-foreground">
                  {step.secret}
                </span>
              </p>
            </CodeStep>
          )}
        </div>
      </div>
    </div>
  );
}

function PasswordStep({
  onLogin,
  onChallenge,
}: {
  onLogin: (
    email: string,
    password: string,
  ) => Promise<{ status: string; challenge?: string; session?: string }>;
  onChallenge: (
    email: string,
    challenge: string,
    session: string,
  ) => Promise<void>;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      const res = await onLogin(values.email, values.password);
      if (res.status === "mfa" && res.challenge && res.session) {
        await onChallenge(values.email, res.challenge, res.session);
      }
      // On "ok" the auth context has already redirected (role-aware).
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setFormError("That email or password doesn't match our records.");
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <>
      <h1 className="mb-6 text-center text-base font-semibold">
        Sign in to your practice account
      </h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            {...register("email")}
          />
          {errors.email && (
            <p className="text-sm text-destructive">{errors.email.message}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
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
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        Don&rsquo;t have an account?{" "}
        <Link
          href="/get-started"
          className="font-medium text-foreground hover:underline"
        >
          Get started
        </Link>
      </p>
    </>
  );
}

function NewPasswordStep({
  onSubmit,
  onChallenge,
}: {
  onSubmit: (
    newPassword: string,
  ) => Promise<{ status: string; challenge?: string; session?: string }>;
  onChallenge: (challenge: string, session: string) => Promise<void>;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<NewPasswordValues>({ resolver: zodResolver(newPasswordSchema) });
  const current = useWatch({ control, name: "newPassword" }) ?? "";

  const submit = async (values: NewPasswordValues) => {
    setFormError(null);
    try {
      const res = await onSubmit(values.newPassword);
      if (res.status === "mfa" && res.challenge && res.session) {
        await onChallenge(res.challenge, res.session);
      }
      // On "ok" the auth context has already redirected (role-aware).
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 400) {
        // Cognito's policy message, relayed by the API (never echoes the password).
        setFormError(
          String(err.response.data?.detail ?? "That password isn't allowed."),
        );
      } else if (axios.isAxiosError(err) && err.response?.status === 401) {
        setFormError("Your sign-in session expired. Please sign in again.");
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <>
      <h1 className="text-center text-base font-semibold">
        Choose your password
      </h1>
      <p className="mt-2 mb-6 text-center text-sm text-muted-foreground">
        You signed in with a temporary password. Set your own to continue.
      </p>
      <form onSubmit={handleSubmit(submit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="newPassword">New password</Label>
          <Input
            id="newPassword"
            type="password"
            autoComplete="new-password"
            autoFocus
            {...register("newPassword")}
          />
          {errors.newPassword && (
            <p className="text-sm text-destructive">
              {errors.newPassword.message}
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm">Confirm password</Label>
          <Input
            id="confirm"
            type="password"
            autoComplete="new-password"
            {...register("confirm")}
          />
          {errors.confirm && (
            <p className="text-sm text-destructive">{errors.confirm.message}</p>
          )}
        </div>
        <ul
          className="space-y-1 text-xs text-muted-foreground"
          aria-label="Password requirements"
        >
          {PASSWORD_RULES.map((rule) => {
            const ok = rule.test(current);
            return (
              <li
                key={rule.label}
                className={ok ? "text-foreground" : undefined}
              >
                <span aria-hidden className="mr-1.5 inline-block w-3">
                  {ok ? "✓" : "·"}
                </span>
                {rule.label}
              </li>
            );
          })}
        </ul>
        {formError && <p className="text-sm text-destructive">{formError}</p>}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Set password and continue"}
        </Button>
      </form>
    </>
  );
}

function CodeStep({
  title,
  description,
  onSubmit,
  children,
}: {
  title: string;
  description: string;
  onSubmit: (code: string) => Promise<void>;
  children?: React.ReactNode;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onSubmit(code);
      // On success the auth context redirects; leave the button disabled.
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <h1 className="text-center text-base font-semibold">{title}</h1>
      <p className="text-center text-sm text-muted-foreground">{description}</p>
      {children}
      <div className="space-y-1.5">
        <Label htmlFor="code">6-digit code</Label>
        <Input
          id="code"
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
        {busy ? "Verifying…" : "Verify"}
      </Button>
    </form>
  );
}
