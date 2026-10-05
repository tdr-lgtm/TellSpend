/**
 * Rows for "Paid by" and "Split between" in the expense form.
 *
 * A person is ME (you) or a contact id as a string, because that's what a
 * <select> works with. The API uses counterparty_id, with null for you.
 */

import { fromPaise, toPaise } from "./money";

export const ME = "me";

export type PersonRow = {
  key: number; // stable React key, never sent to the API
  person: string;
  amount: string;
  method: string; // payers only; "" = not given
  provider: string; // payers only; "" = not given
};

let lastKey = 0;

export function newRow(person: string = ME, amount = "", method = "", provider = ""): PersonRow {
  lastKey += 1;
  return { key: lastKey, person, amount, method, provider };
}

export function personFromId(counterpartyId: number | null): string {
  return counterpartyId === null ? ME : String(counterpartyId);
}

export function idFromPerson(person: string): number | null {
  return person === ME ? null : Number(person);
}

type SavedRow = {
  counterparty_id: number | null;
  amount: string;
  method?: string | null;
  provider?: string | null;
};

// Saved payments or shares as form rows. None saved yet: just you.
export function rowsFrom(items: SavedRow[]): PersonRow[] {
  if (items.length === 0) {
    return [newRow()];
  }

  return items.map((item) =>
    newRow(personFromId(item.counterparty_id), item.amount, item.method ?? "", item.provider ?? ""),
  );
}

// Each row's amount in paise, checked against the total. A single row
// always gets the whole total. Returns the amounts, or an error message.
export function rowAmounts(rows: PersonRow[], totalPaise: number, what: string): number[] | string {
  if (rows.length === 1) {
    return [totalPaise];
  }

  const amounts: number[] = [];

  for (const row of rows) {
    const paise = toPaise(row.amount);

    if (!paise) {
      return `${what}: enter an amount for everyone.`;
    }

    amounts.push(paise);
  }

  const sum = amounts.reduce((total, paise) => total + paise, 0);

  if (sum !== totalPaise) {
    return `${what}: amounts add up to ${fromPaise(sum)} but the expense is ${fromPaise(totalPaise)}.`;
  }

  return amounts;
}

// ["You", "Parth", "Riya"] -> "You, Parth & Riya"
export function joinNames(names: string[]): string {
  if (names.length <= 1) {
    return names.join("");
  }

  return `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}`;
}
