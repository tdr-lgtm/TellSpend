/**
 * One expense as the assistant understood it, for the user to check.
 *
 *   Save            stores it exactly as shown (adding any new contacts)
 *   Edit first      opens the normal expense form with these values
 *                   (adding the draft's new people as contacts first, so
 *                   every payment and share goes into the form)
 *   Discard         drops the card
 *
 * A draft with problems can't be saved as is: the problems say what's
 * unclear. The user answers them in words (the draft is read again), or
 * fixes it by hand in the form.
 */

import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useCategoryLabel } from "../hooks/useCategories";
import { useConfirmDraft } from "../hooks/useAssistant";
import { useToast } from "../hooks/useToast";
import { createCounterparty, type AssistantResult, type Counterparty, type DraftPerson, type ExpenseDraft } from "../lib/api";
import { categoryStyle } from "../lib/categoryStyle";
import { describeAdjustments } from "../lib/adjustments";
import { withContacts } from "../lib/drafts";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney } from "../lib/format";
import { paymentMethodLabel } from "../lib/paymentMethods";
import { joinNames } from "../lib/people";
import AnswerBox from "./AnswerBox";
import type { Thread } from "./AnswerBox";
import Button from "./Button";

type DraftCardProps = {
  draft: ExpenseDraft;
  onDone: () => void; // saved or discarded: remove the card
  // Repayments from the same message already saved, which settle it.
  settlementIds?: number[];
  onSaved?: (expenseId: number) => void;
  // Open it in the expense form instead; its new people are contacts by then.
  onEdit: (draft: ExpenseDraft) => void;
  thread: Thread; // what it was read from, and answers so far
  // Its questions were answered: the drafts that replace it.
  onAnswered: (result: AssistantResult, thread: Thread) => void;
};

function personLabel(person: DraftPerson): string {
  return person.kind === "new" ? `${person.name} (new)` : person.name;
}

// "3 bags rice @ ₹210.00 ₹630.00 (Aadhya)": quantity, unit and unit price
// kept apart from the line's total, then whose it is.
function describeItem(
  item: ExpenseDraft["items"][number],
  owners: ExpenseDraft["item_owners"][number],
  money: (amount: string) => string,
): string {
  const count = Number(item.quantity);
  const quantity = count !== 1 || item.unit ? `${count}${item.unit ? ` ${item.unit}` : ""} ` : "";
  const each = item.unit_price && count !== 1 ? ` @ ${money(item.unit_price)}` : "";
  const whose =
    owners.length === 1
      ? ` (${personLabel(owners[0].person)})`
      : owners.length > 1
        ? ` (${owners.map((owner) => `${personLabel(owner.person)} ${money(owner.share_amount)}`).join(", ")})`
        : "";
  return `${quantity}${item.name}${each} ${money(item.amount)}${whose}`;
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-16 shrink-0 text-slate-400">{label}</dt>
      <dd className="min-w-0 text-slate-700">{children}</dd>
    </div>
  );
}

export default function DraftCard({ draft, onDone, settlementIds, onSaved, onEdit, thread, onAnswered }: DraftCardProps) {
  const confirm = useConfirmDraft();
  const toast = useToast();
  const categoryLabel = useCategoryLabel();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const newPeople = draft.new_contacts.filter((contact) => contact.counterparty_type === "PERSON");
  const newMerchants = draft.new_contacts.filter((contact) => contact.counterparty_type !== "PERSON");
  const [addError, setAddError] = useState<unknown>(null);

  const money = (amount: string) => formatMoney(amount, draft.currency);
  const hasProblems = draft.problems.length > 0 || draft.amount === null;
  const label = categoryLabel(draft.category);

  const onlyYouShare =
    draft.participants.length === 1 && draft.participants[0].person.kind === "me";

  const payers = draft.payments.map((payment) => {
    const how = [payment.method && paymentMethodLabel(payment.method), payment.provider]
      .filter(Boolean)
      .join(", ");
    const amount = draft.payments.length > 1 ? ` ${money(payment.amount)}` : "";

    return `${personLabel(payment.person)}${amount}${how ? ` (${how})` : ""}`;
  });

  // The form only knows contacts: add the people this draft proposes,
  // then open it with every payment and share as the draft has them. A
  // person is only added once the user said they're someone new.
  async function edit() {
    if (draft.new_contacts.length === 0) {
      onEdit(draft);
      return;
    }

    const unconfirmed = draft.new_contacts.filter(
      (contact) => contact.counterparty_type !== "BUSINESS" && !contact.confirmed,
    );
    if (unconfirmed.length > 0) {
      setAddError(new Error(`First say whether ${unconfirmed.map((c) => c.name).join(" and ")} is someone new.`));
      return;
    }

    setAdding(true);
    setAddError(null);
    const created: Record<string, Counterparty> = {};

    try {
      for (const contact of draft.new_contacts) {
        created[contact.key] = await createCounterparty({
          name: contact.name,
          counterparty_type: contact.counterparty_type,
          relation: contact.relation,
        });
      }
    } catch (error) {
      setAddError(error);
    } finally {
      setAdding(false);
      await queryClient.invalidateQueries({ queryKey: ["counterparties"] });
    }

    // Whoever was added stays added, even if a later one failed.
    const resolved = withContacts(draft, created);
    if (resolved.new_contacts.length === 0) {
      onEdit(resolved);
    }
  }

  function save() {
    confirm.mutate(
      { draft, settlementIds },
      {
        onSuccess: (expense) => {
          toast({ message: `Saved “${expense.description ?? "expense"}”` });
          onSaved?.(expense.id);
          onDone();
        },
      },
    );
  }

  return (
    <li
      className={`rounded-2xl border bg-white p-4 ${hasProblems ? "border-amber-200" : "border-slate-200"}`}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-sm font-semibold ${categoryStyle(draft.category).badge}`}
        >
          {label.charAt(0)}
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">
            {draft.description ?? <span className="text-slate-400">No description</span>}
          </p>
          <p className="truncate text-xs text-slate-500">
            {formatDate(draft.date)} · {label}
            {draft.paid_to && ` · to ${personLabel(draft.paid_to)}`}
          </p>
        </div>

        <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
          {draft.amount ? money(draft.amount) : <span className="text-amber-600">Amount?</span>}
        </p>
      </div>

      <dl className="mt-3 space-y-1 pl-12 text-xs">
        {payers.length > 0 && <Detail label="Paid by">{joinNames(payers)}</Detail>}

        {draft.participants.length > 0 && !onlyYouShare && (
          <Detail label="Split">
            {draft.participants
              .map((share) => `${personLabel(share.person)} ${money(share.share_amount)}`)
              .join(" · ")}
          </Detail>
        )}

        {draft.items.length > 0 && (
          <Detail label="Items">
            {draft.items.map((item, index) => describeItem(item, draft.item_owners[index] ?? [], money)).join(" · ")}
          </Detail>
        )}

        {draft.deductions.length > 0 && (
          <Detail label="Less">{describeAdjustments(draft.deductions, money)}</Detail>
        )}

        {draft.refunds.length > 0 && (
          <Detail label="Refunded">
            {draft.refunds
              .map(
                (refund) =>
                  `${money(refund.amount)} to ${personLabel(refund.person)}` +
                  (refund.label ? ` (${refund.label})` : ""),
              )
              .join(" · ")}
          </Detail>
        )}

        {draft.charges.length > 0 && (
          <Detail label="Charges">{describeAdjustments(draft.charges, money)}</Detail>
        )}
      </dl>

      {newPeople.length > 0 && (
        <p className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">
          Saving also adds {joinNames(newPeople.map((contact) => contact.name))} to your people.
        </p>
      )}

      {newMerchants.length > 0 && (
        <p className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">
          Saving also adds {joinNames(newMerchants.map((contact) => contact.name))} to your merchants.
        </p>
      )}

      {draft.notes.length > 0 && (
        <ul className="mt-3 space-y-1 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {draft.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {draft.problems.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2">
          <ul className="space-y-1 text-xs text-amber-900">
            {draft.problems.map((problem) => (
              <li key={problem} className="flex gap-2">
                <span aria-hidden="true">!</span>
                <span>{problem}</span>
              </li>
            ))}
          </ul>
          <AnswerBox
            thread={thread}
            questions={draft.problems}
            choices={draft.choices}
            onAnswered={onAnswered}
            disabled={confirm.isPending || adding}
          />
        </div>
      )}

      {draft.problems.length === 0 && draft.choices.length > 0 && (
        <div className="mt-3">
          <AnswerBox
            thread={thread}
            questions={[]}
            choices={draft.choices}
            onAnswered={onAnswered}
            disabled={confirm.isPending || adding}
            choicesOnly
          />
        </div>
      )}

      <p className="mt-3 truncate text-xs italic text-slate-400" title={draft.excerpt}>
        “{draft.excerpt}”
      </p>

      {(confirm.isError || addError !== null) && (
        <p role="alert" className="mt-2 text-xs text-rose-700">
          {getErrorMessage(confirm.isError ? confirm.error : addError)}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <Button variant="ghost" size="sm" onClick={onDone} disabled={confirm.isPending || adding}>
          Discard
        </Button>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={edit}
            disabled={confirm.isPending || adding}
            title={
              draft.new_contacts.length > 0
                ? `Adds ${joinNames(draft.new_contacts.map((contact) => contact.name))} first`
                : undefined
            }
          >
            {adding ? "Adding people…" : hasProblems ? "Fix by hand" : "Edit first"}
          </Button>
          <Button
            size="sm"
            onClick={save}
            disabled={hasProblems || confirm.isPending}
            title={hasProblems ? "Fix the problems above first" : undefined}
          >
            {confirm.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </li>
  );
}
