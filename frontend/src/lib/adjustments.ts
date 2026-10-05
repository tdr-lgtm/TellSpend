/**
 * What a bill has besides its items, as lines of a kind: charges (tax,
 * fees, tips...) add to it, deductions (discounts, rounding down) take
 * money off its price. Each kind stays its own line; the helpers here
 * work the same way for both lists.
 */

import { fromPaise, toPaise } from "./money";

// A charge or a deduction as the API sends it.
export type Adjustment = {
  kind: string;
  label: string;
  amount: string;
};

export type KindOption = { value: string; label: string };

export function kindLabel(kinds: readonly KindOption[], kind: string, fallback: string): string {
  return kinds.find((option) => option.value === kind)?.label ?? fallback;
}

// "GST 72.00 · Delivery 40.00"
export function describeAdjustments(lines: Adjustment[], money: (amount: string) => string): string {
  return lines.map((line) => `${line.label} ${money(line.amount)}`).join(" · ");
}

export function adjustmentsTotalPaise(lines: { amount: string }[]): number {
  return lines.reduce((total, line) => total + (toPaise(line.amount) ?? 0), 0);
}

export type AdjustmentRow = {
  key: number; // stable React key, never sent to the API
  kind: string;
  label: string; // blank: the kind's own name
  amount: string;
};

let lastKey = 0;

export function newAdjustmentRow(kinds: readonly KindOption[], line?: Adjustment): AdjustmentRow {
  lastKey += 1;

  return {
    key: lastKey,
    kind: line?.kind ?? kinds[0].value,
    // A label that's just the kind's name is shown as blank, so changing
    // the kind doesn't leave a stale name behind.
    label: line && line.label !== kindLabel(kinds, line.kind, "") ? line.label : "",
    amount: line?.amount ?? "",
  };
}

// The rows as API lines, or an error message if any row is incomplete.
export function toAdjustments(rows: AdjustmentRow[], kinds: readonly KindOption[]): Adjustment[] | string {
  const lines: Adjustment[] = [];

  for (const row of rows) {
    const label = row.label.trim().replace(/\s+/g, " ") || kindLabel(kinds, row.kind, row.kind);
    const paise = toPaise(row.amount);

    if (!paise) {
      return `Enter an amount for ${label}.`;
    }

    lines.push({ kind: row.kind, label, amount: fromPaise(paise) });
  }

  return lines;
}
