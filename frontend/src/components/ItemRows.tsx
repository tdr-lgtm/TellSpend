/**
 * Edits the items of an expense: only what was bought. Items keep their
 * full prices, and tax and charges are entered separately, so
 * items - deductions + charges should equal the amount; a status line says
 * whether it does, and offers to set the amount from them.
 */

import { itemsTotalPaise, newItemRow, type ItemRow } from "../lib/items";
import { inputClass } from "../lib/styles";
import { fromPaise } from "../lib/money";

type ItemRowsProps = {
  rows: ItemRow[];
  onChange: (rows: ItemRow[]) => void;
  amountPaise: number | null;
  discountPaise: number;
  chargesPaise: number;
  currency: string;
  onUseAsAmount: (amount: string) => void;
};


export default function ItemRows({
  rows,
  onChange,
  amountPaise,
  discountPaise,
  chargesPaise,
  currency,
  onUseAsAmount,
}: ItemRowsProps) {
  function change(key: number, patch: Partial<ItemRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  const chargedPaise = itemsTotalPaise(rows) - discountPaise + chargesPaise;
  const matches = amountPaise !== null && chargedPaise === amountPaise;

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Items (optional)</legend>

      {rows.map((row) => (
        <div key={row.key} className="grid grid-cols-[1fr_3.5rem_3.5rem_6rem_auto] items-center gap-2">
          <input
            aria-label="Item name"
            placeholder="Item"
            maxLength={255}
            value={row.name}
            onChange={(event) => change(row.key, { name: event.target.value })}
            className={inputClass}
          />
          <input
            aria-label="Quantity"
            inputMode="decimal"
            placeholder="Qty"
            value={row.quantity}
            onChange={(event) => change(row.key, { quantity: event.target.value })}
            className={inputClass}
          />
          <input
            aria-label="Unit"
            placeholder="kg"
            maxLength={20}
            value={row.unit}
            onChange={(event) => change(row.key, { unit: event.target.value })}
            className={inputClass}
          />
          <input
            aria-label="Line price"
            inputMode="decimal"
            placeholder="Price"
            value={row.amount}
            onChange={(event) => change(row.key, { amount: event.target.value })}
            className={inputClass}
          />
          <button
            type="button"
            aria-label="Remove item"
            onClick={() => onChange(rows.filter((other) => other.key !== row.key))}
            className="flex h-10 w-8 items-center justify-center rounded-lg text-lg leading-none text-slate-400 hover:bg-white hover:text-rose-600"
          >
            ×
          </button>
        </div>
      ))}

      <div className="flex flex-wrap items-center gap-4 text-xs font-medium">
        <button
          type="button"
          onClick={() => onChange([...rows, newItemRow()])}
          className="text-slate-600 hover:text-slate-900"
        >
          + Add item
        </button>

        {rows.length > 0 &&
          (matches ? (
            <span className="text-emerald-700">Items match the amount ✓</span>
          ) : (
            <>
              <span className="text-amber-700">
                Items{discountPaise > 0 ? " less deductions" : ""}
                {chargesPaise > 0 ? " plus charges" : ""} come to {fromPaise(Math.max(chargedPaise, 0))}{" "}
                {currency}
              </span>
              {chargedPaise > 0 && (
                <button
                  type="button"
                  onClick={() => onUseAsAmount(fromPaise(chargedPaise))}
                  className="text-slate-600 underline hover:text-slate-900"
                >
                  Use as amount
                </button>
              )}
            </>
          ))}
      </div>
    </fieldset>
  );
}
