/**
 * Edits a list of people with amounts: used for "Paid by" and "Split
 * between". With one row that person covers the whole amount, so no
 * amount box is shown. With several, each needs an amount, and a status
 * line shows how far they are from the total.
 *
 * For payers (`forPayments`), each row also has a method and provider,
 * and the same person may be listed twice (part by card, part in cash).
 */

import { fromPaise, splitEvenly, toPaise } from "../lib/money";
import { PAYMENT_METHODS } from "../lib/paymentMethods";
import { ME, newRow, type PersonRow } from "../lib/people";
import { inputClass } from "../lib/styles";

type Option = {
  value: string;
  label: string;
};

type PeopleRowsProps = {
  legend: string;
  wholeLabel: string; // shown next to a single row, e.g. "paid it all"
  rows: PersonRow[];
  onChange: (rows: PersonRow[]) => void;
  people: Option[];
  totalPaise: number | null;
  currency: string;
  canSplitEqually?: boolean;
  forPayments?: boolean;
};


export default function PeopleRows({
  legend,
  wholeLabel,
  rows,
  onChange,
  people,
  totalPaise,
  currency,
  canSplitEqually = false,
  forPayments = false,
}: PeopleRowsProps) {
  const single = rows.length === 1;
  const used = new Set(rows.map((row) => row.person));

  function change(key: number, patch: Partial<PersonRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addRow() {
    // Someone not listed yet; payers may repeat, so fall back to you.
    const free = people.find((option) => !used.has(option.value));
    onChange([...rows, newRow(free?.value ?? ME)]);
  }

  function splitEqually() {
    if (!totalPaise) {
      return;
    }

    const parts = splitEvenly(totalPaise, rows.length);
    onChange(rows.map((row, index) => ({ ...row, amount: fromPaise(parts[index]) })));
  }

  // With several rows: how far their amounts are from the total.
  let status: { text: string; tone: string } | null = null;

  if (!single && totalPaise) {
    const sum = rows.reduce((total, row) => total + (toPaise(row.amount) ?? 0), 0);
    const difference = totalPaise - sum;

    if (difference === 0) {
      status = { text: "Adds up ✓", tone: "text-emerald-700" };
    } else if (difference > 0) {
      status = { text: `${fromPaise(difference)} ${currency} left to assign`, tone: "text-amber-700" };
    } else {
      status = { text: `${fromPaise(-difference)} ${currency} too much`, tone: "text-rose-700" };
    }
  }

  const canAdd = forPayments || rows.length < people.length;

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{legend}</legend>

      {rows.map((row) => (
        <div key={row.key} className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <select
              aria-label={`${legend}: person`}
              value={row.person}
              onChange={(event) => change(row.key, { person: event.target.value })}
              className={`min-w-0 flex-1 ${inputClass}`}
            >
              {people.map((option) => (
                // A person can't have two shares; a payer can pay in parts.
                <option
                  key={option.value}
                  value={option.value}
                  disabled={!forPayments && option.value !== row.person && used.has(option.value)}
                >
                  {option.label}
                </option>
              ))}
            </select>

            {single ? (
              <span className="shrink-0 text-sm text-slate-500">{wholeLabel}</span>
            ) : (
              <>
                <input
                  aria-label={`${legend}: amount`}
                  inputMode="decimal"
                  placeholder="0.00"
                  value={row.amount}
                  onChange={(event) => change(row.key, { amount: event.target.value })}
                  className={`w-28 ${inputClass}`}
                />
                <button
                  type="button"
                  aria-label="Remove"
                  onClick={() => onChange(rows.filter((other) => other.key !== row.key))}
                  className="flex h-10 w-8 items-center justify-center rounded-lg text-lg leading-none text-slate-400 hover:bg-white hover:text-rose-600"
                >
                  ×
                </button>
              </>
            )}
          </div>

          {forPayments && (
            <div className="grid grid-cols-2 gap-2 pl-3">
              <select
                aria-label={`${legend}: method`}
                value={row.method}
                onChange={(event) => change(row.key, { method: event.target.value })}
                className={inputClass}
              >
                <option value="">Method (optional)</option>
                {PAYMENT_METHODS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                aria-label={`${legend}: bank or app`}
                placeholder="Bank or app (optional)"
                maxLength={100}
                value={row.provider}
                onChange={(event) => change(row.key, { provider: event.target.value })}
                className={inputClass}
              />
            </div>
          )}
        </div>
      ))}

      <div className="flex items-center gap-4 text-xs font-medium">
        {canAdd && (
          <button type="button" onClick={addRow} className="text-slate-600 hover:text-slate-900">
            {forPayments ? "+ Add payment" : "+ Add person"}
          </button>
        )}

        {canSplitEqually && !single && (
          <button
            type="button"
            onClick={splitEqually}
            disabled={!totalPaise}
            className="text-slate-600 hover:text-slate-900 disabled:opacity-50"
          >
            Split equally
          </button>
        )}

        {status && <span className={status.tone}>{status.text}</span>}
      </div>
    </fieldset>
  );
}
