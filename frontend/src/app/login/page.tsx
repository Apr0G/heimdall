"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import axios from "axios";
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

const GLOW = {
  backgroundImage:
    "radial-gradient(90% 60% at 50% 0%, color-mix(in oklab, var(--color-amber-500) 12%, transparent), transparent 60%)",
};

export default function LoginPage() {
  const { login } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setFormError("That email or password doesn't match our records.");
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* Brand bar + header so visitors can click the logo back to the landing page. */}
      <div className="h-1 bg-gradient-to-r from-amber-500 to-blue-500" />
      <MarketingHeader showLogin={false} />
      <div className="relative flex flex-1 items-center justify-center px-4 py-12">
        <div aria-hidden style={GLOW} className="pointer-events-none absolute inset-0" />
        <div className="relative w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-md">
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
              {errors.password && (
                <p className="text-sm text-destructive">{errors.password.message}</p>
              )}
            </div>
            {formError && <p className="text-sm text-destructive">{formError}</p>}
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
