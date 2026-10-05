/**
 * The whole signed-in app on one page:
 *
 *   desktop   left: "Describe it", the month at a glance, every expense
 *             right: People (contacts, who owes whom, payments), sticky
 *   phone     Describe it, overview, People, then expenses, so balances
 *             are never buried under a long list
 *
 * Adding and editing happen in dialogs, so the page itself stays calm.
 */

import { useState } from "react";

import AssistantPanel from "../components/AssistantPanel";
import Button from "../components/Button";
import ErrorBoundary from "../components/ErrorBoundary";
import ExpenseForm from "../components/ExpenseForm";
import ExpensesPanel from "../components/ExpensesPanel";
import Modal from "../components/Modal";
import PeoplePanel from "../components/PeoplePanel";
import SpendingOverview from "../components/SpendingOverview";
import { useMe } from "../hooks/useAuth";
import { useDiscardGuard } from "../hooks/useDiscardGuard";
import { useCreateExpense } from "../hooks/useExpenses";
import { useToast } from "../hooks/useToast";
import type { ExpenseInput } from "../lib/api";
import { draftToInput } from "../lib/drafts";
import { getErrorMessage } from "../lib/errors";
import { todayISO } from "../lib/format";

function greeting(): string {
  const hour = new Date().getHours();

  if (hour < 12) {
    return "Good morning";
  }

  return hour < 17 ? "Good afternoon" : "Good evening";
}

// What the add dialog starts from; onSaved runs after a successful save
// (used to remove the assistant draft it came from).
type Adding = { initial: ExpenseInput; title: string; onSaved?: () => void; warnings?: string[] };

export default function Home() {
  const me = useMe();
  const createExpense = useCreateExpense();
  const toast = useToast();
  const [adding, setAdding] = useState<Adding | null>(null);

  const guard = useDiscardGuard(() => {
    createExpense.reset();
    setAdding(null);
  });

  if (me.isPending) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  if (me.isError) {
    return <p className="text-sm text-rose-700">{getErrorMessage(me.error)}</p>;
  }

  const defaultCurrency = me.data.default_currency;

  function addBlank() {
    setAdding({
      title: "Add expense",
      initial: {
        date: todayISO(),
        amount: "",
        currency: defaultCurrency,
        description: "",
        category: "other",
        counterparty_id: null,
        payments: [],
        participants: [],
        discount_amount: "",
        items: [],
        charges: [],
        deductions: [],
        refunds: [],
      },
    });
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">{greeting()},</p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{me.data.name}</h1>
        </div>
        <Button onClick={addBlank}>+ Add expense</Button>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:grid-rows-[auto_auto_1fr] lg:items-start">
        {/* Each section has its own error boundary: if one breaks, the
            others keep working. */}
        <div className="min-w-0 lg:col-start-1 lg:row-start-1">
          <ErrorBoundary label="the assistant">
            <AssistantPanel
              onEditDraft={(draft, onSaved) =>
                setAdding({
                  title: "Check and save",
                  initial: draftToInput(draft, defaultCurrency),
                  onSaved,
                  // What the assistant still had questions about.
                  warnings: draft.problems.map((problem) => `Still open: ${problem}`),
                })
              }
            />
          </ErrorBoundary>
        </div>

        <div className="min-w-0 lg:col-start-1 lg:row-start-2">
          <ErrorBoundary label="the monthly overview">
            <SpendingOverview />
          </ErrorBoundary>
        </div>

        <div className="lg:sticky lg:top-24 lg:col-start-2 lg:row-span-3 lg:row-start-1">
          <ErrorBoundary label="People">
            <PeoplePanel />
          </ErrorBoundary>
        </div>

        <div className="min-w-0 lg:col-start-1 lg:row-start-3">
          <ErrorBoundary label="the expense list">
            <ExpensesPanel onAdd={addBlank} />
          </ErrorBoundary>
        </div>
      </div>

      {adding && (
        <Modal title={adding.title} onClose={guard.requestClose} discard={guard.prompt}>
          <ExpenseForm
            initial={adding.initial}
            warnings={adding.warnings}
            submitLabel="Add expense"
            isSubmitting={createExpense.isPending}
            error={createExpense.error}
            onDirtyChange={guard.setDirty}
            onSubmit={(values) =>
              createExpense.mutate(values, {
                onSuccess: (expense) => {
                  adding.onSaved?.();
                  guard.close();
                  toast({ message: `Added “${expense.description ?? "expense"}”` });
                },
              })
            }
            onCancel={guard.requestClose}
          />
        </Modal>
      )}
    </>
  );
}
