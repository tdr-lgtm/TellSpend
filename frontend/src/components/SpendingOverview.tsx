/**
 * The month at a glance: what it cost you (your shares), what you paid
 * out, how many expenses, and where the money went by category. One
 * block per currency, since different currencies can't be added up.
 * (What's owed lives in the People panel.)
 */

import { useState } from "react";

import { useCategoryLabel } from "../hooks/useCategories";
import { useSummary } from "../hooks/useSummary";
import type { CurrencySummary } from "../lib/api";
import { categoryStyle } from "../lib/categoryStyle";
import { getErrorMessage } from "../lib/errors";
import { currentMonth, formatMoney, formatMonth, shiftMonth } from "../lib/format";
import { Card } from "./Card";

function Breakdown({ summary }: { summary: CurrencySummary }) {
  const categoryLabel = useCategoryLabel();

  if (summary.by_category.length === 0) {
    return null;
  }

  // Shares of the month, for display only (the server did the maths).
  const total = Number(summary.your_spending);

  return (
    <div className="mt-5">
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-100">
        {summary.by_category.map((entry) => (
          <div
            key={entry.category}
            className={categoryStyle(entry.category).bar}
            style={{ width: `${(Number(entry.amount) / total) * 100}%` }}
          />
        ))}
      </div>

      <ul className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {summary.by_category.map((entry) => (
          <li key={entry.category} className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${categoryStyle(entry.category).bar}`} />
            <span className="min-w-0 flex-1 truncate text-slate-600">{categoryLabel(entry.category)}</span>
            <span className="tabular-nums font-medium text-slate-900">
              {formatMoney(entry.amount, summary.currency)}
            </span>
            <span className="w-9 text-right text-xs tabular-nums text-slate-400">
              {Math.round((Number(entry.amount) / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div title={hint}>
      <p className="text-xs text-slate-500">
        {label}
        {hint && <span className="sr-only"> ({hint})</span>}
      </p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  );
}

export default function SpendingOverview() {
  const [month, setMonth] = useState(currentMonth);
  const summary = useSummary(month);
  const isCurrentMonth = month === currentMonth();

  const [main, ...others] = summary.data?.currencies ?? [];

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold text-slate-900">{formatMonth(month)}</h2>

        <div className="flex items-center gap-1">
          {/* Only offered when you've moved away from this month. */}
          {!isCurrentMonth && (
            <button
              type="button"
              onClick={() => setMonth(currentMonth())}
              className="h-8 rounded-lg px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              Back to this month
            </button>
          )}
          <div className="flex items-center rounded-xl border border-slate-200 p-0.5">
          <button
            type="button"
            aria-label="Previous month"
            onClick={() => setMonth((current) => shiftMonth(current, -1))}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            ‹
          </button>
          <button
            type="button"
            aria-label="Next month"
            disabled={isCurrentMonth}
            onClick={() => setMonth((current) => shiftMonth(current, 1))}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-300 disabled:hover:bg-transparent"
          >
            ›
          </button>
          </div>
        </div>
      </div>

      {summary.isPending && (
        <div role="status" className="mt-5 space-y-3">
          <span className="sr-only">Loading…</span>
          <span className="block h-3 w-20 animate-pulse rounded bg-slate-100" />
          <span className="block h-9 w-48 animate-pulse rounded-lg bg-slate-100" />
          <span className="block h-2 w-full animate-pulse rounded-full bg-slate-100" />
        </div>
      )}

      {summary.isError && <p className="mt-6 text-sm text-rose-700">{getErrorMessage(summary.error)}</p>}

      {main && (
        // Dimmed while showing the previous month as a placeholder.
        <div className={`transition-opacity ${summary.isPlaceholderData ? "opacity-50" : ""}`}>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
            <div>
              <p className="text-xs text-slate-500">Your spending</p>
              <p className="mt-1 text-4xl font-semibold tracking-tight tabular-nums text-slate-900">
                {formatMoney(main.your_spending, main.currency)}
              </p>
              <p className="mt-1 text-xs text-slate-400">Only your share of shared expenses</p>
            </div>

            <div className="flex gap-8">
              <Stat
                label="Paid out"
                hint="Everything you paid, including other people's shares"
                value={formatMoney(main.you_paid, main.currency)}
              />
              <Stat label="Expenses" value={String(main.expense_count)} />
            </div>
          </div>

          {main.by_category.length === 0 && (
            <p className="mt-5 text-sm text-slate-400">Nothing spent this month yet.</p>
          )}

          <Breakdown summary={main} />

          {others
            .filter((other) => other.expense_count > 0)
            .map((other) => (
              <div key={other.currency} className="mt-6 border-t border-slate-100 pt-5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
                  <p className="text-sm text-slate-500">
                    In {other.currency}:{" "}
                    <span className="font-semibold tabular-nums text-slate-900">
                      {formatMoney(other.your_spending, other.currency)}
                    </span>
                  </p>
                  <p className="text-xs text-slate-500">
                    paid {formatMoney(other.you_paid, other.currency)} · {other.expense_count} expense
                    {other.expense_count === 1 ? "" : "s"}
                  </p>
                </div>
                <Breakdown summary={other} />
              </div>
            ))}
        </div>
      )}
    </Card>
  );
}
