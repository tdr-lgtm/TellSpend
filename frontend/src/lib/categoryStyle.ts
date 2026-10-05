/**
 * A colour per category, used for the badge on each expense and the bars
 * in the monthly overview. Class names are written out in full so
 * Tailwind finds them.
 */

type CategoryStyle = {
  badge: string; // soft background + text, for the letter badge
  bar: string; // solid colour, for bars and dots
};

const STYLES: Record<string, CategoryStyle> = {
  food_dining: { badge: "bg-orange-50 text-orange-600", bar: "bg-orange-400" },
  groceries: { badge: "bg-emerald-50 text-emerald-600", bar: "bg-emerald-500" },
  transport: { badge: "bg-sky-50 text-sky-600", bar: "bg-sky-500" },
  shopping: { badge: "bg-pink-50 text-pink-600", bar: "bg-pink-400" },
  bills_utilities: { badge: "bg-amber-50 text-amber-600", bar: "bg-amber-400" },
  rent_housing: { badge: "bg-indigo-50 text-indigo-600", bar: "bg-indigo-500" },
  entertainment: { badge: "bg-violet-50 text-violet-600", bar: "bg-violet-500" },
  travel: { badge: "bg-cyan-50 text-cyan-700", bar: "bg-cyan-500" },
  health: { badge: "bg-rose-50 text-rose-600", bar: "bg-rose-400" },
  education: { badge: "bg-blue-50 text-blue-600", bar: "bg-blue-500" },
  personal_care: { badge: "bg-fuchsia-50 text-fuchsia-600", bar: "bg-fuchsia-400" },
  gifts_donations: { badge: "bg-red-50 text-red-600", bar: "bg-red-400" },
  other: { badge: "bg-slate-100 text-slate-600", bar: "bg-slate-400" },
};

export function categoryStyle(category: string): CategoryStyle {
  return STYLES[category] ?? STYLES.other;
}
