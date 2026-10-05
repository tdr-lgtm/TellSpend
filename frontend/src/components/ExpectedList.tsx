/**
 * "Coming up": money you're expecting to get or pay that hasn't moved
 * yet. It changes no balance; "It happened" records it as a payment
 * (asking the amount when it wasn't known), "Remove" forgets it.
 */

import { useState } from "react";

import { useDeleteExpected, useExpected, useMarkExpectedDone } from "../hooks/useExpected";
import { usePersonName } from "../hooks/useCounterparties";
import { useToast } from "../hooks/useToast";
import type { ExpectedMoney } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney, todayISO } from "../lib/format";
import { expectedSentence } from "../lib/moneyKinds";
import Button from "./Button";

function ExpectedRow({ expected }: { expected: ExpectedMoney }) {
  const personName = usePersonName();
  const done = useMarkExpectedDone();
  const remove = useDeleteExpected();
  const toast = useToast();
  const [amount, setAmount] = useState("");

  const sentence = expectedSentence(expected.direction === "they_pay_me", personName(expected.counterparty_id));
  const needsAmount = expected.amount === null;
  const busy = done.isPending || remove.isPending;

  function happened() {
    done.mutate(
      { id: expected.id, date: todayISO(), amount: needsAmount ? amount.trim() : undefined },
      { onSuccess: () => toast({ message: "Recorded as paid" }) },
    );
  }

  return (
    <li className="px-5 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-slate-800">{sentence}</p>
          <p className="truncate text-xs text-slate-500">
            {expected.due_date ? `Due ${formatDate(expected.due_date)}` : "No date"}
            {expected.note && ` · “${expected.note}”`}
          </p>
        </div>
        <p className="shrink-0 text-sm font-semibold tabular-nums text-slate-900">
          {expected.amount ? formatMoney(expected.amount, expected.currency) : "—"}
        </p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {needsAmount && (
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
            placeholder="How much?"
            aria-label="How much was paid"
            className="h-8 w-28 rounded-lg border border-slate-200 px-2 text-base sm:text-xs"
          />
        )}
        <Button size="sm" variant="secondary" onClick={happened} disabled={busy || (needsAmount && !amount.trim())}>
          It happened
        </Button>
        <Button size="sm" variant="ghost" onClick={() => remove.mutate(expected.id)} disabled={busy}>
          Remove
        </Button>
      </div>
      {(done.isError || remove.isError) && (
        <p role="alert" className="mt-1.5 text-xs text-rose-700">
          {getErrorMessage(done.error ?? remove.error)}
        </p>
      )}
    </li>
  );
}

export default function ExpectedList() {
  const expected = useExpected();

  if (!expected.data || expected.data.length === 0) {
    return null;
  }

  return (
    <div className="border-t border-slate-100">
      <p className="px-5 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Coming up</p>
      <ul className="divide-y divide-slate-100">
        {expected.data.map((item) => (
          <ExpectedRow key={item.id} expected={item} />
        ))}
      </ul>
    </div>
  );
}
