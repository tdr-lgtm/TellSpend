/**
 * The frame shared by the login, signup, forgot/reset password and verify
 * pages: a deep-green brand panel that shows what TellSpend does (a
 * sentence turning into a split), and the form beside it. On phones the
 * panel shrinks to a short branded header above the form.
 *
 * The brand panel uses fixed brand colours (not the theme palette), so it
 * looks the same in light and dark mode.
 */

import type { ReactNode } from "react";

import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";

type AuthLayoutProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
};

const BRAND = "bg-[#0F3D2E]";
const LIME = "text-[#C8F169]";

const POINTS = [
  { title: "Type it or say it", text: "“Dinner 1,200 with Parth, split equally” is all it needs." },
  { title: "Splits to the paisa", text: "Shares, tax, tips and refunds worked out for you." },
  { title: "You check, then it saves", text: "Every amount comes from your words. Nothing is guessed." },
];

/**
 * A message being read into a draft: the product in one picture. The
 * card is the app's real draft card (DraftCard) as it looks in light
 * mode, in fixed colours so the panel is the same in both themes.
 */
function Demo() {
  const row = "flex gap-3";
  const term = "w-16 shrink-0 text-[#94A3B8]";
  return (
    <div className="relative w-full max-w-sm" aria-hidden="true">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-[#ffffff]/10 px-4 py-2.5 text-sm text-[#ffffff] ring-1 ring-[#ffffff]/15 backdrop-blur">
        Dinner 1,200 with Parth, I paid, split equally
      </div>

      <div className="mt-3 rounded-2xl border border-[#E2E8F0] bg-[#ffffff] p-4 shadow-2xl shadow-black/30">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#FFF7ED] text-sm font-semibold text-[#EA580C]">
            F
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[#0F172A]">Dinner with Parth</p>
            <p className="truncate text-xs text-[#64748B]">Today · Food &amp; dining</p>
          </div>
          <p className="shrink-0 text-sm font-semibold tabular-nums text-[#0F172A]">₹1,200.00</p>
        </div>

        <dl className="mt-3 space-y-1 pl-12 text-xs">
          <div className={row}>
            <dt className={term}>Paid by</dt>
            <dd className="text-[#334155]">You</dd>
          </div>
          <div className={row}>
            <dt className={term}>Split</dt>
            <dd className="text-[#334155]">You ₹600.00 · Parth ₹600.00</dd>
          </div>
        </dl>

        <p className="mt-3 truncate text-xs text-[#94A3B8] italic">“Dinner 1,200 with Parth, I paid, split equally”</p>

        <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#F1F5F9] pt-3">
          <span className="inline-flex h-8 items-center px-2.5 text-xs font-medium text-[#64748B]">Discard</span>
          <div className="flex gap-2">
            <span className="inline-flex h-8 items-center rounded-lg px-2.5 text-xs font-medium text-[#334155] ring-1 ring-[#E2E8F0] ring-inset">
              Edit first
            </span>
            <span className="inline-flex h-8 items-center rounded-lg bg-[#0F3D2E] px-3 text-xs font-medium text-[#C8F169] shadow-sm">
              Save
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Glow() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div className="absolute -top-32 -right-24 h-96 w-96 rounded-full bg-[#C8F169]/20 blur-3xl" />
      <div className="absolute -bottom-40 -left-24 h-[28rem] w-[28rem] rounded-full bg-[#10B981]/20 blur-3xl" />
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)",
          backgroundSize: "22px 22px",
        }}
      />
    </div>
  );
}

export default function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      {/* Brand panel: full height on desktop. */}
      <aside className={`relative hidden overflow-hidden ${BRAND} lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16`}>
        <Glow />
        <div className="relative">
          <Logo variant="onBrand" size="lg" />
        </div>

        <div className="relative">
          <h2 className="max-w-md text-4xl leading-[1.1] font-semibold tracking-tight text-[#ffffff] xl:text-5xl">
            Say what you spent.
            <br />
            <span className={LIME}>We’ll do the maths.</span>
          </h2>
          <p className="mt-4 max-w-md text-base text-[#ffffff]/70">
            Track your spending and who owes whom, in plain words.
          </p>

          <div className="mt-10">
            <Demo />
          </div>
        </div>

        <ul className="relative grid gap-5 xl:grid-cols-3">
          {POINTS.map((point) => (
            <li key={point.title} className="flex gap-3 xl:block">
              <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#C8F169]/15 text-xs ${LIME}`}>
                ✓
              </span>
              <div className="xl:mt-2">
                <p className="text-sm font-semibold text-[#ffffff]">{point.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-[#ffffff]/60">{point.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </aside>

      {/* Phones and tablets: a short branded header instead. */}
      <header className={`relative overflow-hidden ${BRAND} px-5 pt-6 pb-10 lg:hidden`}>
        <Glow />
        <div className="relative flex items-center justify-between">
          <Logo variant="onBrand" />
          <ThemeToggle />
        </div>
        <p className="relative mt-6 text-2xl leading-tight font-semibold tracking-tight text-[#ffffff]">
          Say what you spent. <span className={LIME}>We’ll do the maths.</span>
        </p>
      </header>

      {/* The form. */}
      <main className="relative flex min-h-[calc(100vh-11rem)] flex-col overflow-hidden px-5 py-6 sm:px-10 lg:min-h-screen lg:py-10">
        {/* The brand panel's glow, carried softly into this side. */}
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <div className="absolute -top-40 -right-32 h-96 w-96 rounded-full bg-[#C8F169]/25 blur-3xl dark:bg-[#C8F169]/10" />
          <div className="absolute -bottom-40 -left-32 h-96 w-96 rounded-full bg-[#10B981]/15 blur-3xl dark:bg-[#10B981]/10" />
        </div>

        {/* Desktop only: on phones it sits in the green header instead. */}
        <div className="relative hidden justify-end lg:flex">
          <ThemeToggle />
        </div>

        <div className="auth-rise relative mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-4 lg:py-8">
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
          <p className="mt-2 text-sm text-slate-500">{subtitle}</p>

          <div className="mt-8 overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_16px_40px_-16px_rgba(15,61,46,0.25)]">
            {/* The brand's green-to-lime, as a thin line on top. */}
            <div className="h-1 bg-gradient-to-r from-[#0F3D2E] via-[#10B981] to-[#C8F169]" aria-hidden="true" />
            <div className="p-6 sm:p-7">{children}</div>
          </div>

          <p className="mt-6 text-center text-sm text-slate-500">{footer}</p>
        </div>

        <p className="relative text-center text-xs text-slate-400">
          <svg viewBox="0 0 24 24" className="mr-1 -mt-0.5 inline-block h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="4" y="11" width="16" height="10" rx="2" />
            <path d="M8 11V7a4 4 0 0 1 8 0v4" />
          </svg>
          Your words stay yours. Nothing is saved until you check it.
        </p>
      </main>
    </div>
  );
}
