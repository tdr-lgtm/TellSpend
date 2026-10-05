/**
 * Answering a card's questions. When the server knows the exact answers
 * (e.g. whether a stated total or the bill's parts are right) they're
 * buttons, applied exactly; anything else is answered in your own words.
 * Either way the card's description is read again with every answer and
 * choice so far, and what comes back replaces the card.
 *
 *   Enter   send the answer
 */

import { useState } from "react";

import { useClarify } from "../hooks/useAssistant";
import type { AssistantResult, ClarificationTurn, Decision, DraftChoice } from "../lib/api";
import { getErrorMessage } from "../lib/errors";

// What a card was read from, the questions answered about it so far, and
// the choices picked.
export type Thread = {
  text: string; // the whole message
  focus: string | null; // with several things in it, this card's part
  turns: ClarificationTurn[];
  decisions: Decision[];
};

type AnswerBoxProps = {
  thread: Thread;
  questions: string[]; // what the card is asking now
  choices: DraftChoice[]; // exact answers the server can apply
  onAnswered: (result: AssistantResult, thread: Thread) => void;
  disabled?: boolean;
  choicesOnly?: boolean; // optional one-tap extras: no text answer box
};

export default function AnswerBox({ thread, questions, choices, onAnswered, disabled, choicesOnly }: AnswerBoxProps) {
  const [answer, setAnswer] = useState("");
  const [nothingFound, setNothingFound] = useState(false);
  const clarify = useClarify();

  const canSend = answer.trim().length > 0 && !clarify.isPending && !disabled;

  // A choice is sent as an answer too (so the description is read with
  // it), and as a decision the server applies exactly.
  function send(reply: string, decision?: Decision) {
    const next: Thread = {
      text: thread.text,
      focus: thread.focus,
      turns: [...thread.turns, { asked: questions, answer: reply }],
      decisions: decision ? [...thread.decisions, decision] : thread.decisions,
    };
    setNothingFound(false);

    clarify.mutate(
      { text: next.text, turns: next.turns, decisions: next.decisions, focus: next.focus },
      {
        onSuccess: (result) => {
          const found =
            result.expenses.length + result.repayments.length + result.expected.length + result.skipped.length;

          // Nothing came back: keep the card and the answer, so nothing is lost.
          if (found === 0) {
            setNothingFound(true);
            return;
          }

          onAnswered(result, next);
        },
      },
    );
  }

  return (
    <div className="mt-2">
      {choices.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {choices.map((choice) => (
            <button
              key={choice.decision}
              type="button"
              onClick={() => send(choice.label, choice.decision)}
              disabled={clarify.isPending || disabled}
              className="h-8 rounded-lg border border-amber-300 bg-white px-3 text-xs font-medium text-amber-900 transition hover:bg-amber-100 disabled:opacity-40"
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      {!choicesOnly && (
      <form
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) {
            send(answer.trim());
          }
        }}
      >
        <input
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          maxLength={1000}
          placeholder="Answer in your own words"
          aria-label="Answer the questions"
          disabled={clarify.isPending || disabled}
          className="h-9 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-base text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-900/5 disabled:bg-slate-50 sm:text-xs"
        />
        <button
          type="submit"
          disabled={!canSend}
          className="h-9 shrink-0 rounded-lg bg-slate-900 px-3 text-xs font-medium text-white transition hover:bg-slate-800 disabled:opacity-40"
        >
          {clarify.isPending ? "Reading…" : "Answer"}
        </button>
      </form>
      )}

      {clarify.isError && (
        <p role="alert" className="mt-1.5 text-xs text-rose-700">
          {getErrorMessage(clarify.error)}
        </p>
      )}

      {nothingFound && (
        <p role="alert" className="mt-1.5 text-xs text-rose-700">
          With that answer I couldn't find an expense any more. Try saying it another way.
        </p>
      )}
    </div>
  );
}
