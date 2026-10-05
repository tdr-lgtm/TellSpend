/**
 * A dialog: a bottom sheet on phones, a centred panel on wider screens.
 *
 * Closes on Escape, the × button or a click outside (all go through
 * onClose, which may ask first; see useDiscardGuard). While open, the
 * page behind doesn't scroll and the first field gets focus; afterwards
 * focus returns to whatever opened it.
 */

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import Button from "./Button";

type ModalProps = {
  title: string;
  onClose: () => void;
  // Set while asking "Discard your changes?".
  discard?: { onDiscard: () => void; onKeep: () => void };
  children: ReactNode;
};

export default function Modal({ title, onClose, discard, children }: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  // The latest onClose, without re-running the effect on every render.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeRef.current();
      }
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    const firstField = panelRef.current?.querySelector<HTMLElement>("input, select, textarea");
    (firstField ?? panelRef.current)?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      if (opener?.isConnected) {
        opener.focus();
      }
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-[2px]" onClick={onClose} />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl outline-none sm:max-w-lg sm:rounded-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 id={titleId} className="truncate text-[15px] font-semibold text-slate-900">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="-mr-1 flex h-8 w-8 items-center justify-center rounded-lg text-xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ×
          </button>
        </div>

        {discard && (
          <div
            role="alertdialog"
            aria-label="Discard your changes?"
            className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-amber-100 bg-amber-50 px-5 py-3"
          >
            <p className="text-sm text-amber-900">Discard your changes?</p>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={discard.onKeep} autoFocus>
                Keep editing
              </Button>
              <Button variant="danger" size="sm" onClick={discard.onDiscard}>
                Discard
              </Button>
            </div>
          </div>
        )}

        {/* The body scrolls; forms keep their buttons in a sticky footer. */}
        <div className="overflow-y-auto px-5 pt-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
