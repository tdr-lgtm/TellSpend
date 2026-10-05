/**
 * One expense in the list. The whole row is a button: tap it to see and
 * edit the expense in a dialog, where it can also be deleted. Deleting
 * shows an Undo toast, which saves the same expense again.
 */

import { useState } from "react";

import { useCategoryLabel } from "../hooks/useCategories";
import { usePersonName } from "../hooks/useCounterparties";
import { useDiscardGuard } from "../hooks/useDiscardGuard";
import { useRefreshExpenses, useUpdateExpense } from "../hooks/useExpenses";
import { useToast } from "../hooks/useToast";
import {
  createExpense as apiCreateExpense,
  deleteExpense as apiDeleteExpense,
  type Expense,
  type ExpenseInput,
} from "../lib/api";
import { categoryStyle } from "../lib/categoryStyle";
import { chargesTotalPaise } from "../lib/charges";
import { refundsTotalPaise } from "../lib/refunds";
import { getErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/format";
import { paymentMethodLabel } from "../lib/paymentMethods";
import { fromPaise } from "../lib/money";
import { joinNames } from "../lib/people";
import Button from "./Button";
import ExpenseForm from "./ExpenseForm";
import Modal from "./Modal";
import ToSettlementPanel from "./ToSettlementPanel";

// The saved expense in the shape the form (and the API) works with.
function toInput(expense: Expense): ExpenseInput {
  return {
    date: expense.date,
    amount: expense.amount,
    currency: expense.currency,
    description: expense.description ?? "",
    category: expense.category,
    counterparty_id: expense.counterparty_id,
    payments: expense.payments,
    participants: expense.participants,
    discount_amount: expense.discount_amount,
    items: expense.items,
    charges: expense.charges,
    deductions: expense.deductions,
    refunds: expense.refunds,
    note: expense.note ?? null,
  };
}

// "UPI (GPay) · 2 items · − ₹50.00 Coupon · + ₹72.00 GST", or null if none.
function describeDetails(expense: Expense): string | null {
  const methods = expense.payments
    .filter((payment) => payment.method || payment.provider)
    .map((payment) => {
      const method = payment.method ? paymentMethodLabel(payment.method) : "";
      if (method && payment.provider) {
        return `${method} (${payment.provider})`;
      }
      return method || (payment.provider ?? "");
    });

  const parts = [...new Set(methods)];

  if (expense.items.length > 0) {
    parts.push(`${expense.items.length} item${expense.items.length === 1 ? "" : "s"}`);
  }

  // Each kind of deduction by its own name: a refund never reads as a discount.
  if (expense.deductions.length === 1) {
    const [deduction] = expense.deductions;
    parts.push(`− ${formatMoney(deduction.amount, expense.currency)} ${deduction.label}`);
  } else if (expense.deductions.length > 1) {
    parts.push(
      `− ${formatMoney(expense.discount_amount, expense.currency)} ` +
        `(${expense.deductions.map((deduction) => deduction.label).join(", ")})`,
    );
  }

  // Money given back after paying: its own event, never "off".
  if (expense.refunds.length > 0) {
    const refunded = fromPaise(refundsTotalPaise(expense.refunds));
    parts.push(`↩ ${formatMoney(refunded, expense.currency)} refunded`);
  }

  if (expense.charges.length === 1) {
    const [charge] = expense.charges;
    parts.push(`+ ${formatMoney(charge.amount, expense.currency)} ${charge.label}`);
  } else if (expense.charges.length > 1) {
    const added = fromPaise(chargesTotalPaise(expense.charges));
    parts.push(`+ ${formatMoney(added, expense.currency)} tax & charges`);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

export default function ExpenseRow({ expense }: { expense: Expense }) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);
  // Deleting one with repayments linked: asked whether those go too.
  const [askLinked, setAskLinked] = useState(false);
  const linked = expense.settlement_ids?.length ?? 0;

  const updateExpense = useUpdateExpense();
  const refresh = useRefreshExpenses();
  const toast = useToast();
  const categoryLabel = useCategoryLabel();
  const personName = usePersonName();

  const guard = useDiscardGuard(() => {
    updateExpense.reset();
    setDeleteError(null);
    setOpen(false);
  });

  const label = categoryLabel(expense.category);
  const style = categoryStyle(expense.category);
  const details = describeDetails(expense);

  // Who else was involved, in words.
  const others =
    expense.payments.some((payment) => payment.counterparty_id !== null) ||
    expense.participants.some((share) => share.counterparty_id !== null);
  const payers = [...new Set(expense.payments.map((payment) => payment.counterparty_id))];
  const myShare = expense.participants.find((share) => share.counterparty_id === null);

  const meta = [label];
  if (expense.counterparty_id !== null) {
    meta.push(`to ${personName(expense.counterparty_id)}`);
  }
  if (others) {
    meta.push(`paid by ${joinNames(payers.map(personName))}`);
  }

  async function remove(withSettlements?: boolean) {
    if (linked > 0 && withSettlements === undefined) {
      setAskLinked(true);
      return;
    }
    setAskLinked(false);
    const saved = toInput(expense);
    setDeleting(true);
    setDeleteError(null);

    try {
      await apiDeleteExpense(expense.id, withSettlements ?? false);
    } catch (error) {
      setDeleteError(error);
      setDeleting(false);
      return;
    }

    guard.close();
    toast({
      message: `Deleted “${expense.description ?? "expense"}”`,
      action: {
        label: "Undo",
        onClick: async () => {
          try {
            await apiCreateExpense(saved);
            await refresh();
            toast({ message: "Expense restored" });
          } catch (error) {
            toast({ message: getErrorMessage(error), tone: "error" });
          }
        },
      },
    });
    await refresh();
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none"
      >
        <span
          aria-hidden="true"
          className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-semibold ${style.badge}`}
        >
          {label.charAt(0)}
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-900">
            {expense.description ?? <span className="text-slate-400">No description</span>}
          </span>
          <span className="mt-0.5 block truncate text-xs text-slate-500">{meta.join(" · ")}</span>
          {details && <span className="mt-0.5 block truncate text-xs text-slate-400">{details}</span>}
          {expense.note && <span className="mt-0.5 block truncate text-xs italic text-slate-400">{expense.note}</span>}
        </span>

        <span className="shrink-0 text-right">
          <span className="block text-sm font-semibold tabular-nums text-slate-900">
            {formatMoney(expense.amount, expense.currency)}
          </span>
          {others && (
            <span className="mt-0.5 block text-xs tabular-nums text-slate-500">
              {myShare ? `yours ${formatMoney(myShare.share_amount, expense.currency)}` : "not yours"}
            </span>
          )}
        </span>
      </button>

      {open && (
        <Modal title={expense.description ?? "Expense"} onClose={guard.requestClose} discard={guard.prompt}>
          {deleteError != null && (
            <p role="alert" className="mb-4 rounded-xl bg-rose-50 px-3 py-2.5 text-sm text-rose-700">
              {getErrorMessage(deleteError)}
            </p>
          )}
          {askLinked && (
            <div role="alert" className="mb-4 rounded-xl bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
              <p>
                {linked === 1 ? "A repayment was" : `${linked} repayments were`} saved as paying this back. Delete{" "}
                {linked === 1 ? "it" : "them"} too?
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" variant="danger" onClick={() => remove(true)}>
                  Delete {linked === 1 ? "both" : "all"}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => remove(false)}>
                  Keep the {linked === 1 ? "repayment" : "repayments"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setAskLinked(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
          <ToSettlementPanel expense={expense} onDone={guard.close} />
          <ExpenseForm
            initial={toInput(expense)}
            warnings={
              linked > 0
                ? [
                    `${linked === 1 ? "A repayment was" : `${linked} repayments were`} saved as paying this back. ` +
                      "Changing this expense doesn't change them.",
                  ]
                : []
            }
            submitLabel="Save changes"
            isSubmitting={updateExpense.isPending}
            error={updateExpense.error}
            onDirtyChange={guard.setDirty}
            onSubmit={(values) =>
              updateExpense.mutate(
                { id: expense.id, input: values },
                {
                  onSuccess: () => {
                    guard.close();
                    toast({ message: "Changes saved" });
                  },
                },
              )
            }
            onCancel={guard.requestClose}
            onDelete={() => remove()}
            isDeleting={deleting}
          />
        </Modal>
      )}
    </li>
  );
}
