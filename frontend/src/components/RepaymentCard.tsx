/**
 * Money paid back between you and one person, as the assistant read it.
 * Saving records it as a payment in People (a settlement), never as an
 * expense; a repayment with problems can't be saved as is, but its
 * questions can be answered in words (it's then read again).
 */

import { useConfirmRepayment } from "../hooks/useAssistant";
import { useToast } from "../hooks/useToast";
import type { AssistantResult, DraftPerson, RepaymentDraft } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney } from "../lib/format";
import { describeMoney, kindNote } from "../lib/moneyKinds";
import { paymentMethodLabel } from "../lib/paymentMethods";
import AnswerBox from "./AnswerBox";
import type { Thread } from "./AnswerBox";
import Avatar from "./Avatar";
import Button from "./Button";

type RepaymentCardProps = {
  repayment: RepaymentDraft;
  onDone: () => void; // saved or discarded: remove the card
  // The saved expense from the same message it pays back, if any.
  expenseId?: number | null;
  onSaved?: (settlementId: number) => void;
  thread: Thread; // what it was read from, and answers so far
  // Its questions were answered: the drafts that replace it.
  onAnswered: (result: AssistantResult, thread: Thread) => void;
};

function label(person: DraftPerson): string {
  return person.kind === "new" ? `${person.name} (new)` : person.name;
}

export default function RepaymentCard({ repayment, onDone, expenseId, onSaved, thread, onAnswered }: RepaymentCardProps) {
  const confirm = useConfirmRepayment();
  const toast = useToast();

  const fromMe = repayment.from_person.kind === "me";
  const other = fromMe ? repayment.to_person : repayment.from_person;
  // An existing debt runs from who owes to who is owed: worded from the
  // side of who is owed, like a saved one.
  const sentence = describeMoney(repayment.kind, repayment.kind === "balance" ? !fromMe : fromMe, label(other));
  const hasProblems = repayment.problems.length > 0 || repayment.amount === null || !repayment.kind;

  function save() {
    confirm.mutate(
      { repayment, expenseId },
      {
        onSuccess: (settlement) => {
          toast({ message: `Recorded: ${sentence.toLowerCase()}` });
          onSaved?.(settlement.id);
          onDone();
        },
      },
    );
  }

  return (
    <li className={`rounded-2xl border bg-white p-4 ${hasProblems ? "border-amber-200" : "border-slate-200"}`}>
      <div className="flex items-start gap-3">
        <Avatar name={other.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{sentence}</p>
          <p className="truncate text-xs text-slate-500">
            {formatDate(repayment.date)} · {kindNote(repayment.kind)}
            {repayment.method && ` · ${paymentMethodLabel(repayment.method)}`}
          </p>
        </div>
        <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
          {repayment.amount ? (
            formatMoney(repayment.amount, repayment.currency)
          ) : (
            <span className="text-amber-600">Amount?</span>
          )}
        </p>
      </div>

      {repayment.new_contacts.length > 0 && (
        <p className="mt-3 rounded-xl bg-sky-50 px-3 py-2 text-xs text-sky-800">
          Saving also adds {repayment.new_contacts.map((contact) => contact.name).join(" & ")} to
          your people.
        </p>
      )}

      {(repayment.notes ?? []).length > 0 && (
        <ul className="mt-3 space-y-1 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {(repayment.notes ?? []).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      {repayment.problems.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2">
          <ul className="space-y-1 text-xs text-amber-900">
            {repayment.problems.map((problem) => (
              <li key={problem} className="flex gap-2">
                <span aria-hidden="true">!</span>
                <span>{problem}</span>
              </li>
            ))}
          </ul>
          <AnswerBox
            thread={thread}
            questions={repayment.problems}
            choices={repayment.choices ?? []}
            onAnswered={onAnswered}
            disabled={confirm.isPending}
          />
        </div>
      )}

      <p className="mt-3 truncate text-xs italic text-slate-400" title={repayment.excerpt}>
        “{repayment.excerpt}”
      </p>

      {confirm.isError && (
        <p role="alert" className="mt-2 text-xs text-rose-700">
          {getErrorMessage(confirm.error)}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <Button variant="ghost" size="sm" onClick={onDone} disabled={confirm.isPending}>
          Discard
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
    </li>
  );
}
