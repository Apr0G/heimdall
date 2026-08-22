export function formatCents(
  cents: number | null | undefined,
  currency = "USD",
): string {
  if (cents == null) return "—";
  // Integer arithmetic, not `cents / 100`. Hard rule 11 forbids floats for
  // currency. `Intl` formats the integer dollars and the cent digits are
  // spliced in as text, so the result is exact for every safe integer — the
  // input is already a JS number, so nothing beyond 2^53 can arrive here.
  const negative = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100);
  const remainder = abs % 100;
  // Format the integer dollars (exact) and splice the two cent digits in as a
  // string — no double is ever built from the amount.
  const parts = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).formatToParts(dollars);
  const formatted = parts
    .map((p) =>
      p.type === "integer" || p.type === "group" || p.type === "currency"
        ? p.value
        : p.value,
    )
    .join("")
    .replace(/(\d)(?!.*\d)/, `$1.${String(remainder).padStart(2, "0")}`);
  return negative ? `-${formatted}` : formatted;
}

/** Integer cents -> "12.34" for an <input>; the inverse of parseAmountToCents.
 *  Integer arithmetic only (rule 11). */
export function centsToInputString(cents: number | null | undefined): string {
  if (cents == null) return "";
  const abs = Math.abs(Math.trunc(cents));
  const s = `${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
  return cents < 0 ? `-${s}` : s;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Parse as local midnight so a plain date string doesn't shift across zones.
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
