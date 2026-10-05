// Number() is fine here because it's only for showing the amount,
// never for adding amounts up.
export function formatMoney(amount: string, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(Number(amount));
}

// "2026-09-01" -> "1 Sep 2026". Built from parts so it stays the same
// calendar day: new Date("2026-09-01") would be midnight UTC, which is
// the previous day in timezones behind UTC.
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);

  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

// Today's date on this device as "YYYY-MM-DD". Not toISOString(), which
// gives the UTC date and is "yesterday" in India before 5:30 am.
export function todayISO(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  return `${now.getFullYear()}-${month}-${day}`;
}
// This month on this device as "YYYY-MM".
export function currentMonth(): string {
  return todayISO().slice(0, 7);
}

// "2026-01" moved by -1 -> "2025-12".
export function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(year, monthNumber - 1 + delta, 1);

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

// "2026-09" -> "September 2026".
export function formatMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number);

  return new Date(year, monthNumber - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}
