/**
 * The one button style for the whole app, in a few variants and sizes.
 */

import type { ButtonHTMLAttributes } from "react";

import { brandActionClass } from "../lib/styles";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "brand";
type Size = "sm" | "md";

type ButtonProps = {
  variant?: Variant;
  size?: Size;
} & ButtonHTMLAttributes<HTMLButtonElement>;

const VARIANTS: Record<Variant, string> = {
  primary: `${brandActionClass} shadow-sm`,
  secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-50",
  ghost: "text-slate-500 hover:bg-slate-100 hover:text-slate-900",
  danger: "text-rose-600 hover:bg-rose-50",
  // The same as primary (kept as a name the sign-in pages use).
  brand: `${brandActionClass} shadow-sm`,
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-2.5 text-xs",
  md: "h-10 px-4 text-sm",
};

export default function Button({
  variant = "primary",
  size = "md",
  type = "button",
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={
        "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl font-medium transition-colors " +
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-slate-900/10 " +
        `disabled:pointer-events-none disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`
      }
      {...props}
    />
  );
}
