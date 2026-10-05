/**
 * Money between you and someone that hasn't moved yet ("he'll pay me back
 * ₹500 next week"), as the assistant read it. Nothing changes; "Remember
 * it" keeps it under People, to tick off when it happens.
 */

import { useConfirmExpected } from "../hooks/useAssistant";
import { useToast } from "../hooks/useToast";
import type { AssistantResult, DraftPerson, ExpectedDraft } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney } from "../lib/format";
import { expectedSentence } from "../lib/moneyKinds";
import AnswerBox from "./AnswerBox";
import type { Thread } from "./AnswerBox";
import Avatar from "./Avatar";
import Button from "./Button";

type ExpectedCardProps = {
  expected: ExpectedDraft;
  onDone: () => void; // remembered or dismissed: remove the card
  thread: Thread;
  onAnswered: (result: AssistantResult, thread: Thread) => void;
};

function label(person: DraftPerson): string {
  return person.kind === "new" ? `${person.name} (new)` : person.name;
}

export default function ExpectedCard({ expected, onDone, thread, onAnswered }: ExpectedCardProps) {
  const confirm = useConfirmExpected();
  const toast = useToast();

  const theyPayMe = expected.to_person.kind === "me";
  const other = theyPayMe ? expected.from_person : expected.to_person;
  const sentence = expectedSentence(theyPayMe, label(other));
  const hasProblems = expected.problems.length > 0;

  function remember() {
    confirm.mutate(expected, {
      onSuccess: () => {
        toast({ message: "Remembered. Find it under People until it happens." });
        onDone();
      },
    });
  }

  return (
    <li className={`rounded-2xl border bg-white p-4 ${hasProblems ? "border-amber-200" : "border-slate-200"}`}>
      <div className="flex items-start gap-3">
        <Avatar name={other.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900">{sentence}</p>
          <p className="truncate text-xs text-slate-500">
            Hasn't happened yet{expected.due_date && ` · due ${formatDate(expected.due_date)}`}
          </p>
        </div>
        <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
          {expected.amount ? formatMoney(expected.amount, expected.currency) : <span className="text-slate-400">—</span>}
        </p>
      </div>

      <p className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
        Nothing changes until it happens. Remember it to tick it off then.
      </p>

      {expected.problems.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2">
          <ul className="space-y-1 text-xs text-amber-900">
            {expected.problems.map((problem) => (
              <li key={problem} className="flex gap-2">
                <span aria-hidden="true">!</span>
                <span>{problem}</span>
              </li>
            ))}
          </ul>
          <AnswerBox
            thread={thread}
            questions={expected.problems}
            choices={expected.choices}
            onAnswered={onAnswered}
            disabled={confirm.isPending}
          />
        </div>
      )}

      <p className="mt-3 truncate text-xs italic text-slate-400" title={expected.excerpt}>
        “{expected.excerpt}”
      </p>

      {confirm.isError && (
        <p role="alert" className="mt-2 text-xs text-rose-700">
          {getErrorMessage(confirm.error)}
        </p>
      )}

      <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
        <Button variant="ghost" size="sm" onClick={onDone} disabled={confirm.isPending}>
          Dismiss
        </Button>
        <Button size="sm" onClick={remember} disabled={hasProblems || confirm.isPending}>
          {confirm.isPending ? "Saving…" : "Remember it"}
        </Button>
      </div>
    </li>
  );
}
