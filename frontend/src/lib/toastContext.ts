/**
 * The shared "show a toast" function (see ToastProvider).
 */

import { createContext } from "react";

export type Toast = {
  message: string;
  tone?: "success" | "error";
  // An optional button on the toast, e.g. { label: "Undo", onClick }.
  action?: { label: string; onClick: () => void | Promise<unknown> };
};

export const ToastContext = createContext<(toast: Toast) => void>(() => {});
