// Plain-English meanings for the CARC codes Heimdall surfaces on the dashboard.
// Reference data (not PHI); extend as more codes appear.
export const CARC_MEANINGS: Record<string, string> = {
  "CO-4": "Procedure code is inconsistent with the modifier used.",
  "CO-11": "Diagnosis is inconsistent with the procedure.",
  "CO-15": "Authorization number is missing or invalid.",
  "CO-16": "Claim lacks information needed for adjudication (see RARC).",
  "CO-18": "Duplicate claim or service.",
  "CO-29": "Time limit for filing has expired.",
  "CO-45": "Charge exceeds the fee schedule — contractual write-off.",
  "CO-50": "Service is not deemed a medical necessity.",
  "CO-96": "Non-covered charge(s).",
  "CO-97": "Service is bundled into another service (NCCI).",
  "CO-109": "Claim is not covered by this payer or contractor.",
  // CO-150 and CO-151 are DIFFERENT denials and are easily transposed. 150 is
  // about the LEVEL of service (argue E/M level); 151 is about how MANY services
  // (argue units and frequency). 151 previously carried 150's wording here and in
  // the analysis prompt, which steered the appeal at the wrong argument entirely.
  "CO-150": "Information submitted does not support this level of service.",
  "CO-151":
    "Information submitted does not support this many/frequency of services.",
  "CO-167": "Diagnosis is not covered.",
  "CO-197": "Precertification / authorization is absent.",
  "PR-1": "Deductible amount (patient responsibility).",
  "PR-2": "Coinsurance amount (patient responsibility).",
  "PR-3": "Copay amount (patient responsibility).",
  "PR-204": "Not covered under the patient's current plan.",
};

export function carcMeaning(code: string): string {
  return CARC_MEANINGS[code] ?? "Claim adjustment reason code.";
}
