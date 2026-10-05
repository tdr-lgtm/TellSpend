/**
 * Exact money maths for the forms, done in whole paise (cents) so that
 * splitting and adding never suffer float rounding: 0.1 + 0.2 !== 0.3.
 */

// Whole number, or up to 2 decimal places: 350, 99.5, 99.50
const AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

// "1,234.5" -> 123450. Anything that isn't a valid amount -> null.
export function toPaise(text: string): number | null {
  const clean = text.trim().replace(/,/g, "");

  if (!AMOUNT_PATTERN.test(clean)) {
    return null;
  }

  const [whole, fraction = ""] = clean.split(".");

  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

// 123450 -> "1234.50", the string form the API expects.
export function fromPaise(paise: number): string {
  const whole = Math.floor(paise / 100);
  const rest = paise % 100;

  return `${whole}.${String(rest).padStart(2, "0")}`;
}

// Split a total into `parts` shares that differ by at most one paisa and
// add up exactly: 10000 into 3 -> [3334, 3333, 3333].
export function splitEvenly(totalPaise: number, parts: number): number[] {
  const base = Math.floor(totalPaise / parts);
  const extra = totalPaise % parts;

  return Array.from({ length: parts }, (_, index) => base + (index < extra ? 1 : 0));
}
