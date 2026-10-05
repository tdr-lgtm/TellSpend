/**
 * A round badge with someone's initials, tinted by their name so the same
 * person always gets the same colour.
 */

const TINTS = [
  "bg-rose-100 text-rose-700",
  "bg-amber-100 text-amber-800",
  "bg-emerald-100 text-emerald-700",
  "bg-sky-100 text-sky-700",
  "bg-violet-100 text-violet-700",
  "bg-teal-100 text-teal-700",
  "bg-indigo-100 text-indigo-700",
  "bg-orange-100 text-orange-700",
];

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);

  return ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
}

function tint(name: string): string {
  let hash = 0;

  for (const character of name) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }

  return TINTS[hash % TINTS.length];
}

export default function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const sizeClass = size === "sm" ? "h-8 w-8 text-[11px]" : "h-10 w-10 text-xs";

  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${sizeClass} ${tint(name)}`}
    >
      {initials(name)}
    </span>
  );
}
