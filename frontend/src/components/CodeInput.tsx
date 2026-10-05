/**
 * Six boxes for a 6-digit code. Typing moves to the next box, Backspace
 * to the previous one, and pasting the whole code (or the phone filling
 * it in from the SMS/email) fills every box. onComplete runs when all six
 * are filled.
 */

import { useRef } from "react";

const LENGTH = 6;

type CodeInputProps = {
  value: string; // the digits so far, up to 6
  onChange: (value: string) => void;
  onComplete: (code: string) => void;
  disabled?: boolean;
};

export default function CodeInput({ value, onChange, onComplete, disabled }: CodeInputProps) {
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  function focus(index: number) {
    boxes.current[Math.max(0, Math.min(LENGTH - 1, index))]?.focus();
  }

  // Put digits in from box `index` on, keeping the ones before it.
  function fill(index: number, typed: string) {
    const digits = typed.replace(/\D/g, "");
    if (!digits) {
      return;
    }

    const next = (value.slice(0, index) + digits).slice(0, LENGTH);
    onChange(next);
    focus(next.length);

    if (next.length === LENGTH) {
      onComplete(next);
    }
  }

  return (
    <div className="flex justify-between gap-2" role="group" aria-label="6-digit code">
      {Array.from({ length: LENGTH }, (_, index) => (
        <input
          key={index}
          ref={(element) => {
            boxes.current[index] = element;
          }}
          value={value[index] ?? ""}
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          aria-label={`Digit ${index + 1}`}
          maxLength={LENGTH}
          disabled={disabled}
          autoFocus={index === 0}
          onChange={(event) => fill(index, event.target.value)}
          onPaste={(event) => {
            event.preventDefault();
            fill(0, event.clipboardData.getData("text"));
          }}
          onKeyDown={(event) => {
            if (event.key === "Backspace") {
              event.preventDefault();
              // Clear this box, or the one before when this one's empty.
              const at = value[index] ? index : index - 1;
              if (at >= 0) {
                onChange(value.slice(0, at));
                focus(at);
              }
            } else if (event.key === "ArrowLeft") {
              focus(index - 1);
            } else if (event.key === "ArrowRight") {
              focus(index + 1);
            }
          }}
          className="h-12 w-full min-w-0 rounded-xl border border-slate-200 bg-white text-center text-xl font-semibold tabular-nums text-slate-900 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-900/5 disabled:bg-slate-50"
        />
      ))}
    </div>
  );
}
