/**
 * Edits an expense's refunds: money given back after paying, each with
 * who got it back and what it was for. Refunds aren't discounts: the
 * amount stays what was paid, and the split is of what's left after them.
 */

import { newRefundRow, type RefundRow } from "../lib/refunds";
import { inputClass } from "../lib/styles";

type Option = {
  value: string;
  label: string;
};

type RefundRowsProps = {
  rows: RefundRow[];
  onChange: (rows: RefundRow[]) => void;
  people: Option[]; // who can get money back: the people who paid
};

export default function RefundRows({ rows, onChange, people }: RefundRowsProps) {
  function change(key: number, patch: Partial<RefundRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Refunds after paying (optional)
      </legend>

      {rows.map((row) => (
        <div key={row.key} className="grid grid-cols-[7.5rem_1fr_6rem_auto] items-center gap-2">
          <select
            aria-label="Who got it back"
            value={row.person}
            onChange={(event) => change(row.key, { person: event.target.value })}
            className={inputClass}
          >
            {people.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            aria-label="What it was for"
            placeholder="Returned item"
            maxLength={100}
            value={row.label}
            onChange={(event) => change(row.key, { label: event.target.value })}
            className={inputClass}
          />
          <input
            aria-label="Refund amount"
            inputMode="decimal"
            placeholder="Amount"
            value={row.amount}
            onChange={(event) => change(row.key, { amount: event.target.value })}
            className={inputClass}
          />
          <button
            type="button"
            aria-label="Remove refund"
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
          onClick={() => onChange([...rows, newRefundRow(undefined, people[0]?.value)])}
          className="text-slate-600 hover:text-slate-900"
        >
          + Add refund
        </button>
      </div>
    </fieldset>
  );
}
