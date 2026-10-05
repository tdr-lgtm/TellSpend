/**
 * Show a short message at the bottom of the screen, optionally with an
 * action such as Undo: const toast = useToast(); toast({ message }).
 */

import { useContext } from "react";

import { ToastContext } from "../lib/toastContext";

export function useToast() {
  return useContext(ToastContext);
}
