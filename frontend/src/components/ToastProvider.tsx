/**
 * Shows toasts at the bottom of the screen: confirmations ("Expense
 * added") and undoable deletes ("Expense deleted · Undo"). Each toast
 * disappears by itself after a few seconds; at most three are shown.
 */

import { useCallback, useState, type ReactNode } from "react";

import { ToastContext, type Toast } from "../lib/toastContext";

type ShownToast = Toast & { id: number };

const SHOW_FOR_MS = 6000;

let lastId = 0;

export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ShownToast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (toast: Toast) => {
      lastId += 1;
      const id = lastId;

      setToasts((current) => [...current.slice(-2), { ...toast, id }]);
      window.setTimeout(() => dismiss(id), SHOW_FOR_MS);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={show}>
      {children}

      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className="pointer-events-auto flex w-full max-w-sm items-center gap-3 rounded-2xl bg-slate-900 py-2.5 pl-4 pr-2 text-sm text-white shadow-lg"
          >
            <span
              aria-hidden="true"
              className={`h-2 w-2 shrink-0 rounded-full ${toast.tone === "error" ? "bg-rose-400" : "bg-emerald-400"}`}
            />
            <span className="min-w-0 flex-1">{toast.message}</span>

            {toast.action && (
              <button
                type="button"
                onClick={() => {
                  dismiss(toast.id);
                  void toast.action?.onClick();
                }}
                className="rounded-lg px-2.5 py-1 text-sm font-semibold text-white hover:bg-white/10"
              >
                {toast.action.label}
              </button>
            )}

            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => dismiss(toast.id)}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-lg leading-none text-white/50 hover:bg-white/10 hover:text-white"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
