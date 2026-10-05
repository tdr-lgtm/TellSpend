/**
 * One contact in the People panel with their balance. The whole row is a
 * button that opens their card: the balance in words, Settle up, the
 * expenses you share, and edit/delete. Deleting shows an Undo toast; the
 * server refuses to delete someone still used in expenses or payments.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useUpdateCounterparty } from "../hooks/useCounterparties";
import { useDiscardGuard } from "../hooks/useDiscardGuard";
import { useExpenses } from "../hooks/useExpenses";
import { useToast } from "../hooks/useToast";
import {
  createCounterparty,
  deleteCounterparty,
  type Balance,
  type Counterparty,
} from "../lib/api";
import { contactTypeLabel } from "../lib/contacts";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney } from "../lib/format";
import { errorBoxClass } from "../lib/styles";
import Avatar from "./Avatar";
import Button from "./Button";
import ContactForm from "./ContactForm";
import MergeContact from "./MergeContact";
import Modal from "./Modal";

type PersonRowProps = {
  contact: Counterparty;
  balances: Balance[];
  onSettle: (balance: Balance) => void;
};

function subtitleFor(contact: Counterparty): string {
  if (contact.counterparty_type !== "PERSON") {
    return contactTypeLabel(contact.counterparty_type);
  }

  return contact.relation ? `Your ${contact.relation}` : "Person";
}

export default function PersonRow({ contact, balances, onSettle }: PersonRowProps) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState<unknown>(null);

  const queryClient = useQueryClient();
  const updateContact = useUpdateCounterparty();
  const expenses = useExpenses();
  const toast = useToast();

  const refreshContacts = () => queryClient.invalidateQueries({ queryKey: ["counterparties"] });

  const guard = useDiscardGuard(() => {
    updateContact.reset();
    setRemoveError(null);
    setEditing(false);
    setOpen(false);
  });

  const subtitle = subtitleFor(contact);

  // The latest expenses this contact is part of (payer, sharer or "paid to").
  const shared = (expenses.data ?? [])
    .filter(
      (expense) =>
        expense.counterparty_id === contact.id ||
        expense.payments.some((payment) => payment.counterparty_id === contact.id) ||
        expense.participants.some((share) => share.counterparty_id === contact.id),
    )
    .slice(0, 5);

  // Plain API calls rather than a mutation hook: this row disappears as
  // soon as the list refreshes, and the Undo must still work after that.
  async function remove() {
    const saved = {
      name: contact.name,
      counterparty_type: contact.counterparty_type,
      relation: contact.relation,
    };

    setRemoving(true);
    setRemoveError(null);

    try {
      await deleteCounterparty(contact.id);
    } catch (error) {
      // E.g. 409: still used in expenses or payments. Say so, keep them.
      setRemoveError(error);
      setRemoving(false);
      return;
    }

    guard.close();
    toast({
      message: `Removed ${contact.name}`,
      action: {
        label: "Undo",
        onClick: async () => {
          try {
            await createCounterparty(saved);
            await refreshContacts();
            toast({ message: `${contact.name} is back` });
          } catch (error) {
            toast({ message: getErrorMessage(error), tone: "error" });
          }
        },
      },
    });
    await refreshContacts();
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none"
      >
        <Avatar name={contact.name} />

        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-slate-900">{contact.name}</span>
          <span className="block truncate text-xs text-slate-500">{subtitle}</span>
        </span>

        <span className="shrink-0 text-right">
          {balances.length === 0 ? (
            <span className="text-xs text-slate-400">Settled</span>
          ) : (
            balances.map((balance) => {
              const theyOwe = !balance.amount.startsWith("-");
              return (
                <span key={balance.currency} className="block">
                  <span
                    className={`block text-sm font-semibold tabular-nums ${theyOwe ? "text-emerald-600" : "text-amber-600"}`}
                  >
                    {formatMoney(balance.amount.replace("-", ""), balance.currency)}
                  </span>
                  <span className="block text-[11px] text-slate-400">
                    {theyOwe ? "owes you" : "you owe"}
                  </span>
                </span>
              );
            })
          )}
        </span>
      </button>

      {open && (
        <Modal
          title={editing ? `Edit ${contact.name}` : contact.name}
          onClose={guard.requestClose}
          discard={guard.prompt}
        >
          {editing ? (
            <ContactForm
              initial={contact}
              submitLabel="Save changes"
              cancelLabel="Back"
              isSubmitting={updateContact.isPending}
              error={updateContact.error}
              onDirtyChange={guard.setDirty}
              onSubmit={(values) =>
                updateContact.mutate(
                  { id: contact.id, input: values },
                  {
                    onSuccess: () => {
                      guard.setDirty(false);
                      setEditing(false);
                      toast({ message: "Changes saved" });
                    },
                  },
                )
              }
              onCancel={() => {
                updateContact.reset();
                guard.setDirty(false);
                setEditing(false);
              }}
            />
          ) : (
            <div className="flex flex-col gap-5 pb-5">
              <div className="flex items-center gap-3">
                <Avatar name={contact.name} />
                <div className="min-w-0">
                  <p className="truncate text-base font-semibold text-slate-900">{contact.name}</p>
                  <p className="text-sm text-slate-500">{subtitle}</p>
                </div>
              </div>

              <div className="rounded-2xl bg-slate-50 p-4">
                {balances.length === 0 ? (
                  <p className="text-sm text-slate-600">You're all settled up with {contact.name}.</p>
                ) : (
                  balances.map((balance) => {
                    const theyOwe = !balance.amount.startsWith("-");
                    const amount = formatMoney(balance.amount.replace("-", ""), balance.currency);
                    return (
                      <div key={balance.currency} className="flex items-center justify-between gap-3 py-1">
                        <p className="text-sm text-slate-700">
                          {theyOwe ? (
                            <>
                              {contact.name} owes you{" "}
                              <span className="font-semibold text-emerald-600">{amount}</span>
                            </>
                          ) : (
                            <>
                              You owe {contact.name}{" "}
                              <span className="font-semibold text-amber-600">{amount}</span>
                            </>
                          )}
                        </p>
                        <Button
                          size="sm"
                          onClick={() => {
                            guard.close();
                            onSettle(balance);
                          }}
                        >
                          Settle up
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Recent shared expenses
                </p>
                {shared.length === 0 ? (
                  <p className="text-sm text-slate-500">None yet.</p>
                ) : (
                  <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-100">
                    {shared.map((expense) => (
                      <li key={expense.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                        <span className="min-w-0">
                          <span className="block truncate text-sm text-slate-800">
                            {expense.description ?? "Expense"}
                          </span>
                          <span className="block text-xs text-slate-400">{formatDate(expense.date)}</span>
                        </span>
                        <span className="shrink-0 text-sm tabular-nums text-slate-700">
                          {formatMoney(expense.amount, expense.currency)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <MergeContact contact={contact} onDone={guard.close} />

              {removeError != null && (
                <p role="alert" className={errorBoxClass}>
                  {getErrorMessage(removeError)}
                </p>
              )}

              <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-4">
                <Button variant="danger" onClick={remove} disabled={removing}>
                  {removing ? "Removing…" : "Remove"}
                </Button>
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit details
                </Button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </li>
  );
}
