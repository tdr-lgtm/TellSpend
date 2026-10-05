/**
 * Refunds: money given back after paying (a returned or cancelled item).
 * Each is its own event with who got it back, never a discount or a
 * payment: the bill and its payments stay as paid, and the shares are of
 * what's left after the refunds.
 */

import type { Refund } from "./api";
import { fromPaise, toPaise } from "./money";
import { ME, idFromPerson, personFromId } from "./people";

export type RefundRow = {
  key: number; // stable React key, never sent to the API
  person: string; // who got it back: ME or a contact id
  amount: string;
  label: string;
  date: string | null; // kept as saved; null: the expense's date
};

let lastKey = 0;

export function newRefundRow(refund?: Refund, person: string = ME): RefundRow {
  lastKey += 1;

  return {
    key: lastKey,
    person: refund ? personFromId(refund.counterparty_id) : person,
    amount: refund?.amount ?? "",
    label: refund?.label ?? "",
    date: refund?.date ?? null,
  };
}

export function refundsTotalPaise(refunds: { amount: string }[]): number {
  return refunds.reduce((total, refund) => total + (toPaise(refund.amount) ?? 0), 0);
}

// The rows as API refunds, or an error message if any row is incomplete.
export function toRefunds(rows: RefundRow[]): Refund[] | string {
  const refunds: Refund[] = [];

  for (const row of rows) {
    const paise = toPaise(row.amount);

    if (!paise) {
      return "Enter an amount for each refund.";
    }

    refunds.push({
      counterparty_id: idFromPerson(row.person),
      amount: fromPaise(paise),
      label: row.label.trim().replace(/\s+/g, " ") || null,
      date: row.date,
    });
  }

  return refunds;
}
