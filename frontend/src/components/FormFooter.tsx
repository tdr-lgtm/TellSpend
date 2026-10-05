/**
 * The button row at the bottom of a form in a dialog. It sticks to the
 * bottom while the form scrolls, so Save is always in reach. `start`
 * holds a secondary action on the left, e.g. Delete.
 */

import type { ReactNode } from "react";

export default function FormFooter({ start, children }: { start?: ReactNode; children: ReactNode }) {
  return (
    <div className="sticky bottom-0 -mx-5 mt-2 flex items-center justify-between gap-2 border-t border-slate-100 bg-white px-5 py-3.5 pb-[max(0.875rem,env(safe-area-inset-bottom))]">
      <div>{start}</div>
      <div className="flex gap-2">{children}</div>
    </div>
  );
}
