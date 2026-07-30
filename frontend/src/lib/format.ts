export function formatCents(cents: number | null | undefined, currency = "USD"): string {
  if (cents == null) return "—";
  // Integer arithmetic, not `cents / 100`. Hard rule 11 forbids floats for
  // currency, and a float division is the exact shape of the bug that rule exists
  // to prevent — correct at today's magnitudes, silently wrong at some larger
  // one. `Intl` still does the locale formatting; it just receives exact parts.
  const negative = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100);
  const remainder = abs % 100;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(`${dollars}.${String(remainder).padStart(2, "0")}`));
  return negative ? `-${formatted}` : formatted;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Parse as local midnight so a plain date string doesn't shift across zones.
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
