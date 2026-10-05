/**
 * The microphone button next to a text box: tap to speak, tap again (or
 * pause) to stop. Not shown where the browser can't do speech to text.
 */

import { speechSupported } from "../lib/speech";

type MicButtonProps = {
  listening: boolean;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
  size?: "md" | "lg";
};

export default function MicButton({ listening, onStart, onStop, disabled, size = "lg" }: MicButtonProps) {
  if (!speechSupported) {
    return null;
  }

  const box = size === "lg" ? "h-12 w-12" : "h-11 w-11";

  return (
    <button
      type="button"
      onClick={listening ? onStop : onStart}
      disabled={disabled}
      aria-pressed={listening}
      aria-label={listening ? "Stop listening" : "Speak instead of typing"}
      title={listening ? "Listening… tap to stop" : "Speak instead of typing"}
      className={`relative flex ${box} shrink-0 items-center justify-center rounded-xl border transition disabled:opacity-40 ${
        listening
          ? "border-rose-200 bg-rose-50 text-rose-600"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
      }`}
    >
      {listening && <span className="absolute inset-0 animate-ping rounded-xl bg-rose-200/60" aria-hidden="true" />}
      <svg viewBox="0 0 24 24" className="relative h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}
           strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
    </button>
  );
}
