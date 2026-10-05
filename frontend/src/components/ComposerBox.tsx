/**
 * The chat-style box you type (or speak) expenses into. It starts one
 * line tall and grows with the text (up to 200px, or 35% of a short phone
 * screen), then scrolls inside.
 *
 *   Enter          send
 *   Shift + Enter  new line
 *
 * The mic button fills the box as you talk; what's spoken and what it
 * means for the box is up to the caller.
 */

import { type ReactNode, type RefObject, useLayoutEffect, useRef } from "react";

import MicButton from "./MicButton";

type ComposerBoxProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
  submitLabel: string; // e.g. "Read"
  loadingLabel: string; // e.g. "Reading…"
  placeholder: string;
  ariaLabel: string;
  maxLength?: number;
  listening: boolean;
  onStartSpeaking: () => void;
  onStopSpeaking: () => void;
  error: string | null;
  hint: ReactNode; // under the box, left; hidden on phones
  extra?: ReactNode; // under the box, right
  textareaRef?: RefObject<HTMLTextAreaElement | null>;
};

// The tallest the box grows before it scrolls inside.
function maxHeight(): number {
  return Math.min(200, Math.round(window.innerHeight * 0.35));
}

export default function ComposerBox({
  value,
  onChange,
  onSubmit,
  isLoading,
  submitLabel,
  loadingLabel,
  placeholder,
  ariaLabel,
  maxLength,
  listening,
  onStartSpeaking,
  onStopSpeaking,
  error,
  hint,
  extra,
  textareaRef,
}: ComposerBoxProps) {
  const ownRef = useRef<HTMLTextAreaElement>(null);
  const ref = textareaRef ?? ownRef;

  // Grow with the text; past the maximum, scroll inside instead.
  useLayoutEffect(() => {
    const textarea = ref.current;

    if (!textarea) {
      return;
    }

    const limit = maxHeight();
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, limit)}px`;
    textarea.style.overflowY = textarea.scrollHeight > limit ? "auto" : "hidden";
  }, [value, ref]);

  const canSend = value.trim().length > 0 && !isLoading;

  return (
    <div>
      <form
        className="flex items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) {
            onSubmit();
          }
        }}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter adds a new line.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (canSend) {
                onSubmit();
              }
            }
          }}
          rows={1}
          maxLength={maxLength}
          placeholder={placeholder}
          aria-label={ariaLabel}
          className="block min-h-12 w-full min-w-0 resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 text-base leading-6 text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-900/5 sm:text-sm"
        />

        <MicButton listening={listening} onStart={onStartSpeaking} onStop={onStopSpeaking} disabled={isLoading} />

        <button
          type="submit"
          disabled={!canSend}
          className="h-12 shrink-0 rounded-xl bg-slate-900 px-5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-40"
        >
          {isLoading ? loadingLabel : submitLabel}
        </button>
      </form>

      {error ? (
        <p role="alert" className="mt-2 text-xs text-rose-600">
          {error}
        </p>
      ) : (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <p className="hidden text-[11px] text-slate-400 sm:block">{hint}</p>
          {extra}
        </div>
      )}
    </div>
  );
}
