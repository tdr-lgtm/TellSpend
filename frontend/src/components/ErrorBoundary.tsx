/**
 * Catches a crash while drawing one part of the page, so only that part
 * shows "Something went wrong" (with Try again) instead of the whole app
 * turning white. The error is logged to the browser console.
 *
 * (React only supports this as a class component.)
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

type ErrorBoundaryProps = {
  // What the broken part is called, e.g. "the expense list".
  label: string;
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Crash in ${this.props.label}:`, error, info.componentStack);
  }

  render() {
    if (this.state.error === null) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800"
      >
        <p className="font-medium">Something went wrong in {this.props.label}.</p>
        <p className="mt-1 text-rose-700">The rest of the app still works.</p>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="mt-3 rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100"
        >
          Try again
        </button>
      </div>
    );
  }
}
