/**
 * The centered card shared by the login and signup pages.
 */

import type { ReactNode } from "react";

import Logo from "./Logo";

type AuthLayoutProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
};

export default function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4 py-10">
      <Logo />

      <h1 className="mt-8 text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
      <p className="mt-1.5 text-sm text-slate-500">{subtitle}</p>

      <div className="mt-6 rounded-2xl border border-slate-200/80 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        {children}
      </div>

      <p className="mt-5 text-center text-sm text-slate-500">{footer}</p>
    </main>
  );
}
