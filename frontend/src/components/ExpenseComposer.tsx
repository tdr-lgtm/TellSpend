/**
 * The chat-style box where expenses are described in words (see
 * ComposerBox), with voice input.
 *
 *   Enter          read it
 *   Shift + Enter  new line
 *
 * Or speak: the mic button fills the box as you talk. Spoken words are
 * added to what's already typed; nothing is read until Read.
 */

import { useRef } from "react";

import { useDictation } from "../hooks/useVoice";
import { joinText } from "../lib/speech";
import ComposerBox from "./ComposerBox";

type ExpenseComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
  error: string | null;
};

export default function ExpenseComposer({
  value,
  onChange,
  onSubmit,
  isLoading,
  error,
}: ExpenseComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Spoken words go after whatever was in the box when speaking began.
  const typedBefore = useRef("");
  const dictation = useDictation((spoken) => onChange(joinText(typedBefore.current, spoken)));

  function startSpeaking() {
    typedBefore.current = value;
    dictation.start();
    textareaRef.current?.focus();
  }

  // A long hint wraps and gets cut off in the one-line box on phones.
  const narrow = window.matchMedia("(max-width: 639px)").matches;
  const placeholder = narrow
    ? "e.g. Lunch 350 with Parth"
    : "Describe an expense, e.g. “Lunch with Parth ₹1,200, split equally”";

  return (
    <ComposerBox
      value={value}
      onChange={onChange}
      onSubmit={onSubmit}
      isLoading={isLoading}
      submitLabel="Read"
      loadingLabel="Reading…"
      placeholder={placeholder}
      ariaLabel="Describe an expense"
      maxLength={2000}
      listening={dictation.listening}
      onStartSpeaking={startSpeaking}
      onStopSpeaking={dictation.stop}
      error={error ?? dictation.error}
      textareaRef={textareaRef}
      hint={
        dictation.listening
          ? "Listening… speak your expense; it stops when you pause"
          : "Enter to read · Shift + Enter for a new line · nothing is saved until you check it"
      }
    />
  );
}
