/**
 * The expense assistant, at the top of the page: the composer, and below
 * it a card for everything it read: each expense, each repayment (money
 * paid back, saved as a payment in People), and a note for anything it
 * can't record. Nothing is saved until you press Save on a card; cards go
 * once each is saved or discarded. A card with questions can be answered
 * in words: it's then replaced, in place, by what the answers make of it.
 */

import { useState } from "react";

import { usePreviewExpenses } from "../hooks/useAssistant";
import type { AssistantResult, ExpectedDraft, ExpenseDraft, RepaymentDraft } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { sameExcerpt } from "../lib/excerpts";
import type { Thread } from "./AnswerBox";
import { Card } from "./Card";
import DraftCard from "./DraftCard";
import ExpectedCard from "./ExpectedCard";
import ExpenseComposer from "./ExpenseComposer";
import RepaymentCard from "./RepaymentCard";

// Each card gets a stable key, so removing one doesn't disturb the state
// (e.g. "Saving…") of the others.
// Each draft keeps what it was read from and the answers so far (thread).
type Entry =
  | { key: number; type: "expense"; draft: ExpenseDraft; thread: Thread }
  | { key: number; type: "repayment"; repayment: RepaymentDraft; thread: Thread }
  | { key: number; type: "expected"; expected: ExpectedDraft; thread: Thread }
  | { key: number; type: "skipped"; message: string };

// What was saved from the cards so far, so an expense and the repayment
// for it from the same message are saved linked, whichever goes first.
type Saved = {
  expenses: { excerpt: string; id: number }[];
  repayments: { settles: string; id: number }[];
};

let lastKey = 0;

function nextKey(): number {
  lastKey += 1;
  return lastKey;
}

// The cards for what was read. Answering a card's questions reads the
// whole message again (so nothing it said about that part is lost); with
// several things in it, only what's about the card's own part comes back.
function toEntries(result: AssistantResult, text: string): Entry[] {
  const single = result.expenses.length + result.repayments.length + result.expected.length === 1;
  const thread = (excerpt: string): Thread => ({
    text,
    focus: single ? null : excerpt,
    turns: [],
    decisions: [],
  });

  return [
    ...result.expenses.map((draft) => ({
      key: nextKey(),
      type: "expense" as const,
      draft,
      thread: thread(draft.excerpt),
    })),
    ...result.repayments.map((repayment) => ({
      key: nextKey(),
      type: "repayment" as const,
      repayment,
      thread: thread(repayment.excerpt),
    })),
    ...result.expected.map((expected) => ({
      key: nextKey(),
      type: "expected" as const,
      expected,
      thread: thread(expected.excerpt),
    })),
    ...result.skipped.map((message) => ({ key: nextKey(), type: "skipped" as const, message })),
  ];
}

type AssistantPanelProps = {
  // Open a draft in the normal expense form; onSaved is called if the
  // user saves it there (then the card goes). Cancelling keeps the card.
  onEditDraft: (draft: ExpenseDraft, onSaved: () => void) => void;
};

export default function AssistantPanel({ onEditDraft }: AssistantPanelProps) {
  const [text, setText] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [nothingFound, setNothingFound] = useState(false);
  const [saved, setSaved] = useState<Saved>({ expenses: [], repayments: [] });
  const preview = usePreviewExpenses();

  // A saved expense this repayment pays back, and repayments saved for this expense.
  const expenseFor = (repayment: RepaymentDraft) =>
    repayment.settles_excerpt
      ? (saved.expenses.find((expense) => sameExcerpt(expense.excerpt, repayment.settles_excerpt ?? ""))?.id ?? null)
      : null;
  const settlementsFor = (draft: ExpenseDraft) =>
    saved.repayments.filter((repayment) => sameExcerpt(repayment.settles, draft.excerpt)).map((r) => r.id);

  function read() {
    setNothingFound(false);

    preview.mutate(text, {
      onSuccess: (result) => {
        // Read: the box is free for the next one. (On an error the text
        // stays, so nothing typed is lost.)
        setText("");

        const found = toEntries(result, text);

        setNothingFound(found.length === 0);
        setEntries((current) => [...current, ...found]);
      },
    });
  }

  function remove(key: number) {
    setEntries((current) => current.filter((other) => other.key !== key));
  }

  function setDraft(key: number, draft: ExpenseDraft) {
    setEntries((current) =>
      current.map((entry) => (entry.key === key && entry.type === "expense" ? { ...entry, draft } : entry)),
    );
  }

  // A card's questions were answered: what came back takes its place,
  // carrying the answers and choices so far.
  function replace(key: number, result: AssistantResult, thread: Thread) {
    const found = toEntries(result, thread.text).map((entry) =>
      entry.type === "skipped" ? entry : { ...entry, thread },
    );

    setEntries((current) =>
      current.flatMap((entry) => (entry.key === key ? found : [entry])),
    );
  }

  const toCheck = entries.filter((entry) => entry.type !== "skipped").length;

  return (
    <Card className="p-5">
      <h2 className="text-[15px] font-semibold text-slate-900">Describe it</h2>
      <p className="mt-0.5 mb-3 text-xs text-slate-500">
        Write what you spent or paid back, in your own words. You'll check it before anything is
        saved.
      </p>

      <ExpenseComposer
        value={text}
        onChange={setText}
        onSubmit={read}
        isLoading={preview.isPending}
        error={preview.isError ? getErrorMessage(preview.error) : null}
      />

      {preview.isPending && (
        <div role="status" className="mt-4">
          <span className="sr-only">Reading…</span>
          <span className="block h-24 animate-pulse rounded-2xl bg-slate-100" />
        </div>
      )}

      {nothingFound && !preview.isPending && entries.length === 0 && (
        <p className="mt-4 rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-500">
          I couldn't find an expense or repayment in that. Try saying what it was and how much.
        </p>
      )}

      {entries.length > 0 && (
        <>
          {toCheck > 0 && (
            <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {toCheck === 1 ? "Check this" : `Check these ${toCheck}`}
            </p>
          )}
          <ul className="mt-2 flex flex-col gap-3">
            {entries.map((entry) => {
              if (entry.type === "expense") {
                return (
                  <DraftCard
                    key={entry.key}
                    draft={entry.draft}
                    onDone={() => remove(entry.key)}
                    settlementIds={settlementsFor(entry.draft)}
                    onSaved={(id) =>
                      setSaved((current) => ({
                        ...current,
                        expenses: [...current.expenses, { excerpt: entry.draft.excerpt, id }],
                      }))
                    }
                    onEdit={(draft) => {
                      // Its new people are contacts now; the card keeps
                      // that, so saving it later doesn't add them again.
                      setDraft(entry.key, draft);
                      onEditDraft(draft, () => remove(entry.key));
                    }}
                    thread={entry.thread}
                    onAnswered={(result, thread) => replace(entry.key, result, thread)}
                  />
                );
              }

              if (entry.type === "repayment") {
                return (
                  <RepaymentCard
                    key={entry.key}
                    repayment={entry.repayment}
                    onDone={() => remove(entry.key)}
                    expenseId={expenseFor(entry.repayment)}
                    onSaved={(id) => {
                      const settles = entry.repayment.settles_excerpt;
                      if (settles) {
                        setSaved((current) => ({ ...current, repayments: [...current.repayments, { settles, id }] }));
                      }
                    }}
                    thread={entry.thread}
                    onAnswered={(result, thread) => replace(entry.key, result, thread)}
                  />
                );
              }

              if (entry.type === "expected") {
                return (
                  <ExpectedCard
                    key={entry.key}
                    expected={entry.expected}
                    onDone={() => remove(entry.key)}
                    thread={entry.thread}
                    onAnswered={(result, thread) => replace(entry.key, result, thread)}
                  />
                );
              }

              return (
                <li
                  key={entry.key}
                  className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
                >
                  <p className="text-sm text-slate-600">{entry.message}</p>
                  <button
                    type="button"
                    aria-label="Dismiss"
                    onClick={() => remove(entry.key)}
                    className="-mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-slate-400 hover:bg-white hover:text-slate-700"
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Card>
  );
}
