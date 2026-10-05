/**
 * Every expense, newest first, grouped by day. Search matches the
 * description, category and people; the category filter asks the server.
 */

import { useState } from "react";

import { useCategories, useCategoryLabel } from "../hooks/useCategories";
import { usePersonName } from "../hooks/useCounterparties";
import { useExpenses } from "../hooks/useExpenses";
import type { Expense } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatDate, todayISO } from "../lib/format";
import { inputClass } from "../lib/styles";
import Button from "./Button";
import { Card, CardHeader } from "./Card";
import ExpenseRow from "./ExpenseRow";
import SelectField from "./SelectField";
import SkeletonRows from "./SkeletonRows";

function isoDaysAgo(days: number): string {
  const [year, month, day] = todayISO().split("-").map(Number);
  const date = new Date(year, month - 1, day - days);

  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

// "Today", "Yesterday", or "12 Sep 2026".
function dayLabel(isoDate: string): string {
  if (isoDate === isoDaysAgo(0)) {
    return "Today";
  }

  return isoDate === isoDaysAgo(1) ? "Yesterday" : formatDate(isoDate);
}

// The list is already sorted by date, so consecutive runs are the days.
function groupByDay(expenses: Expense[]): { date: string; expenses: Expense[] }[] {
  const groups: { date: string; expenses: Expense[] }[] = [];

  for (const expense of expenses) {
    const last = groups[groups.length - 1];

    if (last && last.date === expense.date) {
      last.expenses.push(expense);
    } else {
      groups.push({ date: expense.date, expenses: [expense] });
    }
  }

  return groups;
}

export default function ExpensesPanel({ onAdd }: { onAdd: () => void }) {
  const categories = useCategories();
  const categoryLabel = useCategoryLabel();
  const personName = usePersonName();

  // "" means all categories.
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const expenses = useExpenses(categoryFilter || undefined);

  const query = search.trim().toLowerCase();

  // Everything a user might type to find an expense.
  function matches(expense: Expense): boolean {
    if (!query) {
      return true;
    }

    const people = [
      expense.counterparty_id,
      ...expense.payments.map((payment) => payment.counterparty_id),
      ...expense.participants.map((share) => share.counterparty_id),
    ]
      .filter((id): id is number => id !== null)
      .map(personName);

    return [expense.description ?? "", categoryLabel(expense.category), expense.amount, ...people]
      .join(" ")
      .toLowerCase()
      .includes(query);
  }

  const shown = (expenses.data ?? []).filter(matches);
  const filtering = Boolean(query || categoryFilter);

  return (
    <Card>
      <CardHeader
        title="Expenses"
        subtitle={
          expenses.isSuccess
            ? filtering
              ? `${shown.length} of ${expenses.data.length} shown`
              : `${shown.length} ${shown.length === 1 ? "expense" : "expenses"}`
            : undefined
        }
      />

      <div className="flex flex-col gap-2 px-5 pt-4 sm:flex-row">
        <input
          type="search"
          aria-label="Search expenses"
          placeholder="Search by name, person or amount"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className={`${inputClass} h-9! sm:flex-1`}
        />
        <SelectField
          aria-label="Filter by category"
          value={categoryFilter}
          onChange={(event) => setCategoryFilter(event.target.value)}
          className="h-9! sm:w-48!"
          options={[
            { value: "", label: "All categories" },
            ...(categories.data ?? []).map((category) => ({
              value: category.key,
              label: category.label,
            })),
          ]}
        />
      </div>

      <div className="mt-4 pb-2">
        {expenses.isPending && <SkeletonRows rows={4} />}

        {expenses.isError && (
          <p className="px-5 py-6 text-sm text-rose-700">{getErrorMessage(expenses.error)}</p>
        )}

        {expenses.isSuccess && shown.length === 0 && (
          <div className="flex flex-col items-center gap-3 border-t border-slate-100 px-5 py-12 text-center">
            {filtering ? (
              <>
                <p className="text-sm text-slate-500">No expenses match.</p>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setSearch("");
                    setCategoryFilter("");
                  }}
                >
                  Clear filters
                </Button>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-700">No expenses yet</p>
                <p className="-mt-2 text-sm text-slate-500">
                  Add what you spend, and split it with people when you share.
                </p>
                <Button size="sm" onClick={onAdd}>
                  + Add your first expense
                </Button>
              </>
            )}
          </div>
        )}

        {shown.length > 0 && (
          // Dimmed while showing the previous filter's list as a placeholder.
          <div className={`transition-opacity ${expenses.isPlaceholderData ? "opacity-50" : ""}`}>
            {groupByDay(shown).map((group) => (
              <section key={group.date} aria-label={dayLabel(group.date)}>
                <h3 className="border-t border-slate-100 bg-slate-50/70 px-5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {dayLabel(group.date)}
                </h3>
                <ul className="divide-y divide-slate-100">
                  {group.expenses.map((expense) => (
                    <ExpenseRow key={expense.id} expense={expense} />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
