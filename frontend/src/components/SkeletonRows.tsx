/**
 * Grey placeholder rows shown while a list loads, shaped like the real
 * rows so the page doesn't jump when the data arrives.
 */

export default function SkeletonRows({ rows = 3, round = false }: { rows?: number; round?: boolean }) {
  return (
    <div role="status">
      <span className="sr-only">Loading…</span>
      <ul aria-hidden="true" className="divide-y divide-slate-100">
        {Array.from({ length: rows }, (_, index) => (
          <li key={index} className="flex items-center gap-3 px-5 py-3.5">
            <span className={`h-9 w-9 shrink-0 animate-pulse bg-slate-100 ${round ? "rounded-full" : "rounded-xl"}`} />
            <span className="flex-1 space-y-2">
              <span className="block h-3 w-1/3 animate-pulse rounded bg-slate-100" />
              <span className="block h-2.5 w-1/2 animate-pulse rounded bg-slate-100" />
            </span>
            <span className="h-3 w-14 animate-pulse rounded bg-slate-100" />
          </li>
        ))}
      </ul>
    </div>
  );
}
