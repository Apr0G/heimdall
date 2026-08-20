"use client";

import axios from "axios";
import { CheckIcon, DotIcon } from "lucide-react";
import type {
  Control,
  FieldErrors,
  FieldValues,
  Path,
  UseFormRegister,
} from "react-hook-form";
import { useWatch } from "react-hook-form";
import { z } from "zod";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Mirrors the Cognito pool's password_policy in main.tf. Cognito is the enforcer;
// this just gives the user the rules up front instead of after a round-trip.
export const PASSWORD_RULES = [
  { label: "At least 12 characters", test: (p: string) => p.length >= 12 },
  { label: "An uppercase letter", test: (p: string) => /[A-Z]/.test(p) },
  { label: "A lowercase letter", test: (p: string) => /[a-z]/.test(p) },
  { label: "A number", test: (p: string) => /\d/.test(p) },
  { label: "A symbol", test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

export const newPasswordField = z
  .string()
  .refine(
    (p) => PASSWORD_RULES.every((r) => r.test(p)),
    "Password doesn't meet the rules below",
  );

/** Zod shape for a new-password + confirm pair; spread into a larger schema. */
export const passwordPairSchema = z
  .object({ newPassword: newPasswordField, confirm: z.string() })
  .refine((v) => v.newPassword === v.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });

/** Turn an API error from any password endpoint into a sentence for the form.
 *  400 carries Cognito's own policy text (never the password); the rest is ours. */
export function passwordErrorText(
  err: unknown,
  unauthorizedText: string,
): string {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    if (status === 400) {
      return String(
        err.response?.data?.detail ?? "That password isn't allowed.",
      );
    }
    if (status === 401) return unauthorizedText;
    if (status === 429)
      return "Too many attempts. Please wait a while and try again.";
  }
  return "Something went wrong. Please try again.";
}

/** New password + confirm inputs with a live rule checklist. Works inside any
 *  react-hook-form whose values include `newPassword` and `confirm`. */
export function NewPasswordFields<
  T extends FieldValues & { newPassword: string; confirm: string },
>({
  register,
  control,
  errors,
  autoFocus,
}: {
  register: UseFormRegister<T>;
  control: Control<T>;
  errors: FieldErrors<T>;
  autoFocus?: boolean;
}) {
  const current =
    (useWatch({ control, name: "newPassword" as Path<T> }) as
      string | undefined) ?? "";
  const newPasswordError = errors.newPassword?.message as string | undefined;
  const confirmError = errors.confirm?.message as string | undefined;

  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="newPassword">New password</Label>
        <Input
          id="newPassword"
          type="password"
          autoComplete="new-password"
          autoFocus={autoFocus}
          {...register("newPassword" as Path<T>)}
        />
        {newPasswordError && (
          <p className="text-sm text-destructive">{newPasswordError}</p>
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm">Confirm new password</Label>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          {...register("confirm" as Path<T>)}
        />
        {confirmError && (
          <p className="text-sm text-destructive">{confirmError}</p>
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
              className={`flex items-center gap-1.5 ${ok ? "text-foreground" : ""}`}
            >
              {ok ? (
                <CheckIcon
                  aria-hidden
                  className="size-3.5 text-emerald-600 dark:text-emerald-400"
                />
              ) : (
                <DotIcon aria-hidden className="size-3.5" />
              )}
              {rule.label}
            </li>
          );
        })}
      </ul>
    </>
  );
}
