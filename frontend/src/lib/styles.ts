/**
 * Class names shared by every input, so all forms look the same.
 * (text-base on phones stops iOS zooming into a focused input.)
 */

export const inputClass =
  "h-10 w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 text-base text-slate-900 " +
  "placeholder:text-slate-400 outline-none transition sm:text-sm " +
  "focus:border-slate-400 focus:ring-4 focus:ring-slate-900/5 disabled:bg-slate-50 disabled:text-slate-400";

export const labelClass = "flex min-w-0 flex-col gap-1.5 text-xs font-medium text-slate-600";

export const errorBoxClass = "rounded-xl bg-rose-50 px-3 py-2.5 text-sm text-rose-700";
