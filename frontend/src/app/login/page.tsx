"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { useForm } from "react-hook-form";
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

// After a correct password, Cognito may require a TOTP code (enrolled) or a
// first-time enrollment (MFA_SETUP). We carry the email + Cognito session through.
type Step =
  | { name: "password" }
  | { name: "code"; email: string; session: string }
  | { name: "setup"; email: string; session: string; secret: string };

const GLOW = {
  backgroundImage:
    "radial-gradient(90% 60% at 50% 0%, color-mix(in oklab, var(--color-amber-500) 12%, transparent), transparent 60%)",
};

function errorText(err: unknown): string {
  if (axios.isAxiosError(err) && (err.response?.status === 401 || err.response?.status === 400)) {
    return "That code didn't match, or it expired. Try again.";
  }
  return "Something went wrong. Please try again.";
}

export default function LoginPage() {
  const { login, verifyMfa, startMfaSetup, completeMfaSetup } = useAuth();
  const [step, setStep] = useState<Step>({ name: "password" });

  return (
    <div className="flex min-h-screen flex-col">
      {/* Brand bar + header so visitors can click the logo back to the landing page. */}
      <div className="h-1 bg-gradient-to-r from-amber-500 to-blue-500" />
      <MarketingHeader showLogin={false} />
      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        <div aria-hidden style={GLOW} className="pointer-events-none absolute inset-0" />
        <div className="relative w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-md">
          {step.name === "password" && (
            <PasswordStep
              onLogin={login}
              onChallenge={async (email, challenge, session) => {
                if (challenge === "MFA_SETUP") {
                  const s = await startMfaSetup(email, session);
                  setStep({ name: "setup", email, session: s.session, secret: s.secret });
                } else {
                  setStep({ name: "code", email, session });
                }
              }}
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
              onSubmit={(code) => completeMfaSetup(step.email, step.session, code)}
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
                <span className="font-mono break-all text-foreground">{step.secret}</span>
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
  onLogin: (email: string, password: string) => Promise<{ status: string; challenge?: string; session?: string }>;
  onChallenge: (email: string, challenge: string, session: string) => Promise<void>;
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
      // On "ok" the auth context has already redirected to /dashboard.
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
      <h1 className="mb-6 text-center text-base font-semibold">Sign in to your practice account</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" autoFocus {...register("email")} />
          {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            {...register("password")}
          />
          {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
        </div>
        {formError && <p className="text-sm text-destructive">{formError}</p>}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        Don&rsquo;t have an account?{" "}
        <Link href="/get-started" className="font-medium text-foreground hover:underline">
          Get started
        </Link>
      </p>
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
          onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
          className="text-center font-mono tracking-[0.4em]"
        />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" className="w-full" disabled={busy || code.length < 6}>
        {busy ? "Verifying…" : "Verify"}
      </Button>
    </form>
  );
}
