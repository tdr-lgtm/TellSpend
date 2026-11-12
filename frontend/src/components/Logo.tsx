/**
 * The TellSpend mark (a speech bubble with a rupee sign, the same as the
 * favicon in public/favicon.svg) and name.
 *
 * "default" follows the theme (colours from index.css, swapped in dark
 * mode like the favicon); "onBrand" is for the deep-green brand panel.
 */

type LogoProps = {
  variant?: "default" | "onBrand";
  size?: "md" | "lg";
  // Only the mark on very small phones (under 360px wide); the name stays
  // for screen readers.
  compact?: boolean;
};

export default function Logo({ variant = "default", size = "md", compact = false }: LogoProps) {
  const onBrand = variant === "onBrand";
  const bubble = onBrand ? "#C8F169" : "var(--logo-bubble)";
  const mark = onBrand ? "#0F3D2E" : "var(--logo-mark)";

  return (
    <span className="inline-flex items-center gap-2">
      <svg viewBox="0 0 100 100" className={size === "lg" ? "h-10 w-10" : "h-8 w-8"} aria-hidden="true">
        <path
          fill={bubble}
          d="M30 6 H70 A24 24 0 0 1 94 30 V58 A24 24 0 0 1 70 82 H46 L22 97 V80 A20 20 0 0 1 6 60 V30 A24 24 0 0 1 30 6 Z"
        />
        <g fill="none" stroke={mark} strokeWidth="9" strokeLinecap="round" strokeLinejoin="round">
          <path d="M35 26 H65" />
          <path d="M35 39 H65" />
          <path d="M43 26 C63 26 63 52 43 52" />
          <path d="M43 52 L61 66" />
        </g>
      </svg>
      <span
        className={`font-semibold tracking-tight ${size === "lg" ? "text-lg" : "text-[15px]"} ${
          onBrand ? "text-[#ffffff]" : "text-slate-900"
        } ${compact ? "max-[359px]:sr-only" : ""}`}
      >
        TellSpend
      </span>
    </span>
  );
}
