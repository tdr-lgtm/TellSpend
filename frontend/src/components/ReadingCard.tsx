/**
 * Shown while the assistant reads a description: a card shaped like the
 * draft that's coming, with a line saying what it's doing (the real
 * steps: read the words, work out the money, check every amount).
 */

import { useEffect, useState } from "react";

const STEPS = [
  "Reading your words…",
  "Working out who paid and who owes…",
  "Checking every amount against what you wrote…",
];

function Bar({ className }: { className: string }) {
  return <span className={`shimmer block rounded-md ${className}`} />;
}

export default function ReadingCard() {
  const [step, setStep] = useState(0);

  // Next step every couple of seconds; stays on the last one.
  useEffect(() => {
    if (step >= STEPS.length - 1) return;
    const timer = window.setTimeout(() => setStep((s) => s + 1), 2200);
    return () => window.clearTimeout(timer);
  }, [step]);

  return (
    <div role="status" aria-live="polite" className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2.5">
        <span className="relative flex h-5 w-5 items-center justify-center" aria-hidden="true">
          <span className="absolute inset-0 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
        </span>
        <span key={step} className="step-in text-sm font-medium text-slate-700">
          {STEPS[step]}
        </span>
      </div>

      {/* The shape of the draft that's coming. */}
      <div className="mt-4 flex items-start justify-between gap-4" aria-hidden="true">
        <div className="flex-1 space-y-2">
          <Bar className="h-3.5 w-2/5" />
          <Bar className="h-2.5 w-1/4" />
        </div>
        <Bar className="h-5 w-24" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2" aria-hidden="true">
        <Bar className="h-10 w-full rounded-xl" />
        <Bar className="h-10 w-full rounded-xl" />
      </div>
    </div>
  );
}
