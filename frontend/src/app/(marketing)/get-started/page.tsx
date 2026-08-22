"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Please enter your name").max(100),
  email: z.string().email("Enter a valid email").max(200),
  practice: z.string().min(1, "Tell us a little about your practice").max(2000),
});

type FormValues = z.infer<typeof schema>;

export default function GetStartedPage() {
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await api.post("/api/leads", values);
      setSubmitted(true);
    } catch {
      setFormError(
        "Something went wrong — please try again, or email us directly.",
      );
    }
  };

  if (submitted) {
    return (
      <section className="mx-auto max-w-lg px-4 py-20 text-center">
        <div className="rounded-xl border border-border bg-card p-10 shadow-md">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-amber-500/15 text-2xl text-amber-600">
            ✓
          </div>
          <h1 className="mt-4 text-2xl font-extrabold tracking-tight">
            Thanks — we&rsquo;ll be in touch soon.
          </h1>
          <p className="mt-2 leading-relaxed text-muted-foreground">
            We&rsquo;ve got your details, and someone from Heimdall will reach
            out shortly to get your practice set up.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-lg px-4 py-16">
      <div className="rounded-xl border border-border bg-card p-8 shadow-md">
        <h1 className="text-3xl font-extrabold tracking-tight">Get started</h1>
        <p className="mt-2 text-muted-foreground">
          Tell us a bit about your practice and we&rsquo;ll set you up. No
          commitment.
        </p>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="mt-6 space-y-4"
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="name">Your name</Label>
            <Input id="name" autoFocus {...register("name")} />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="practice">About your practice</Label>
            <textarea
              id="practice"
              rows={4}
              placeholder="Specialty, size, and what your denial / appeal workload looks like."
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none"
              {...register("practice")}
            />
            {errors.practice && (
              <p className="text-sm text-destructive">
                {errors.practice.message}
              </p>
            )}
          </div>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send"}
          </Button>
        </form>
      </div>
    </section>
  );
}
