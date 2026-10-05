/**
 * Edits one list of a bill's adjustments, each line of its own kind:
 * charges (tax, service charge, delivery, tips, fees) or deductions
 * (discounts, rounding down). Both are kept apart from the items,
 * and the bill is items - deductions + charges.
 */

import { kindLabel, newAdjustmentRow, type AdjustmentRow, type KindOption } from "../lib/adjustments";
import { inputClass } from "../lib/styles";

type AdjustmentRowsProps = {
  rows: AdjustmentRow[];
  onChange: (rows: AdjustmentRow[]) => void;
  kinds: readonly KindOption[];
  legend: string; // "Tax & charges (optional)"
  noun: string; // "charge": for labels such as "Remove charge"
  addLabel: string; // "+ Add tax or charge"
};

export default function AdjustmentRows({ rows, onChange, kinds, legend, noun, addLabel }: AdjustmentRowsProps) {
  function change(key: number, patch: Partial<AdjustmentRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {legend}
      </legend>

      {rows.map((row) => (
        <div key={row.key} className="grid grid-cols-[7.5rem_1fr_6rem_auto] items-center gap-2">
          <select
            aria-label={`Kind of ${noun}`}
            value={row.kind}
            onChange={(event) => change(row.key, { kind: event.target.value })}
            className={inputClass}
          >
            {kinds.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            aria-label="Name on the bill"
            placeholder={kindLabel(kinds, row.kind, "")}
            maxLength={100}
            value={row.label}
            onChange={(event) => change(row.key, { label: event.target.value })}
            className={inputClass}
          />
          <input
            aria-label={`${noun.charAt(0).toUpperCase()}${noun.slice(1)} amount`}
            inputMode="decimal"
            placeholder="Amount"
            value={row.amount}
            onChange={(event) => change(row.key, { amount: event.target.value })}
            className={inputClass}
          />
          <button
            type="button"
            aria-label={`Remove ${noun}`}
            onClick={() => onChange(rows.filter((other) => other.key !== row.key))}
            className="flex h-10 w-8 items-center justify-center rounded-lg text-lg leading-none text-slate-400 hover:bg-white hover:text-rose-600"
          >
            ×
          </button>
        </div>
      ))}

      <div className="text-xs font-medium">
        <button
          type="button"
          onClick={() => onChange([...rows, newAdjustmentRow(kinds)])}
          className="text-slate-600 hover:text-slate-900"
        >
          {addLabel}
        </button>
      </div>
    </fieldset>
  );
}
