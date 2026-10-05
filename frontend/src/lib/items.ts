/**
 * Bill lines in the expense form. Everything is kept as typed text until
 * the form is submitted; then it's checked and turned into API items.
 */

import type { Item } from "./api";
import { fromPaise, toPaise } from "./money";

export type ItemRow = {
  key: number; // stable React key, never sent to the API
  name: string;
  quantity: string;
  unit: string;
  amount: string;
  unitPrice: string; // kept from the saved line; sent only while it still fits
  owners: NonNullable<Item["owners"]>; // whose it is; kept while its price is unchanged
  ownedAmount: string; // the price the owners add up to
};

// Up to 3 decimals, like the database: 2, 1.5, 0.250
const QUANTITY_PATTERN = /^\d+(\.\d{1,3})?$/;

let lastKey = 0;

export function newItemRow(item?: Item): ItemRow {
  lastKey += 1;

  return {
    key: lastKey,
    name: item?.name ?? "",
    // "2.000" from the API reads better as "2".
    quantity: item ? String(Number(item.quantity)) : "1",
    unit: item?.unit ?? "",
    amount: item?.amount ?? "",
    unitPrice: item?.unit_price ?? "",
    owners: item?.owners ?? [],
    ownedAmount: item?.amount ?? "",
  };
}

// The typed-in lines' total in paise, counting unreadable amounts as 0.
export function itemsTotalPaise(rows: ItemRow[]): number {
  return rows.reduce((total, row) => total + (toPaise(row.amount) ?? 0), 0);
}

// The lines as API items, or an error message if any line is incomplete.
export function toItems(rows: ItemRow[]): Item[] | string {
  const items: Item[] = [];

  for (const row of rows) {
    const name = row.name.trim();
    const paise = toPaise(row.amount);
    const quantity = row.quantity.trim() || "1";

    if (!name) {
      return "Every item needs a name.";
    }

    if (!paise) {
      return `Enter a price for ${name}.`;
    }

    if (!QUANTITY_PATTERN.test(quantity) || Number(quantity) === 0) {
      return `The quantity of ${name} should be like 2 or 1.5.`;
    }

    // A unit price is kept only while quantity x unit price is still the
    // line's price (within a paisa a unit); after an edit it's dropped.
    const each = toPaise(row.unitPrice);
    const fits = each !== null && Math.abs(each * Number(quantity) - paise) <= Math.max(Number(quantity), 1);

    items.push({
      name,
      quantity,
      unit: row.unit.trim() || null,
      amount: fromPaise(paise),
      unit_price: each && fits ? fromPaise(each) : null,
      // Whose it is stays while the price does (the owners add up to it).
      owners: row.owners.length > 0 && toPaise(row.ownedAmount) === paise ? row.owners : [],
    });
  }

  return items;
}
