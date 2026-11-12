/**
 * Light, dark, or whatever the device uses. The choice is kept in this
 * browser (localStorage) and applied as the .dark class on <html>; the
 * colours themselves are in index.css. index.html applies it once before
 * the page draws, so there's no flash of the wrong theme.
 */

export type ThemeChoice = "light" | "dark" | "system";

const KEY = "tellspend-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
// The browser bar on phones, matching each theme's page colour.
const BAR_COLOUR = { light: "#ffffff", dark: "#0d1016" };

export function getThemeChoice(): ThemeChoice {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    // Storage blocked (private mode): fall back to the device's setting.
  }
  return "system";
}

function resolve(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function applyTheme(choice: ThemeChoice): void {
  const theme = resolve(choice);
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BAR_COLOUR[theme]);
}

export function setThemeChoice(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    // Not saved, but still applied for this visit.
  }
  applyTheme(choice);
}

/** Re-applies "system" when the device switches between light and dark. */
export function followSystemTheme(): () => void {
  const media = window.matchMedia(DARK_QUERY);
  const onChange = () => {
    if (getThemeChoice() === "system") applyTheme("system");
  };
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
