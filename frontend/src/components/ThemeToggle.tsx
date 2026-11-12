/**
 * Three small buttons: light, dark, or follow the device.
 */

import { useEffect, useState, type ReactNode } from "react";

import { followSystemTheme, getThemeChoice, setThemeChoice, type ThemeChoice } from "../lib/theme";
import { brandActionClass } from "../lib/styles";

const ICON = "h-4 w-4";

const OPTIONS: { value: ThemeChoice; label: string; icon: ReactNode }[] = [
  {
    value: "light",
    label: "Light",
    icon: (
      <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    ),
  },
  {
    value: "dark",
    label: "Dark",
    icon: (
      <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    ),
  },
  {
    value: "system",
    label: "Same as device",
    icon: (
      <svg viewBox="0 0 24 24" className={ICON} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </svg>
    ),
  },
];

export default function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(getThemeChoice);

  useEffect(() => followSystemTheme(), []);

  return (
    <div role="radiogroup" aria-label="Theme" className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
      {OPTIONS.map((option) => {
        const active = option.value === choice;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={option.label}
            title={option.label}
            onClick={() => {
              setThemeChoice(option.value);
              setChoice(option.value);
            }}
            className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
              active ? brandActionClass : "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            }`}
          >
            {option.icon}
          </button>
        );
      })}
    </div>
  );
}
