/**
 * A notice at the top of the screen while the server is waking up from
 * sleep, so the first request after a while doesn't look stuck or broken.
 */

import { useServerWaking } from "../lib/serverWake";

export default function ServerWakeBanner() {
  const waking = useServerWaking();

  if (!waking) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-0 top-0 z-[70] flex justify-center p-3 pt-[max(0.75rem,env(safe-area-inset-top))]"
    >
      <div className="flex max-w-md items-center gap-3 rounded-2xl bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg">
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-white/30 border-t-white"
        />
        <span>
          Waking up the server… The free host sleeps when idle, so this can take up to a minute.
        </span>
      </div>
    </div>
  );
}
