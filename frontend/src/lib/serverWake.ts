/**
 * Whether the API server is still waking up.
 *
 * The free host (Render) puts the server to sleep when nobody uses it, and
 * the first request after that waits about a minute while it starts. Until
 * the server has answered once, a request that's taking a while is shown as
 * "waking up the server…" instead of looking stuck, and a failure from the
 * host while it boots (no answer, 502/503/504) is retried instead of shown.
 */

import { useSyncExternalStore } from "react";

// A request taking longer than this, before the server has ever answered,
// is taken to be waiting for the server to start.
export const SLOW_AFTER_MS = 3000;

// How long to keep retrying while the server boots, from the first try.
export const WAKE_BUDGET_MS = 120_000;

let awake = false;
let pending = 0;
let slow = false;
let slowTimer: number | undefined;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function waking(): boolean {
  return !awake && slow && pending > 0;
}

export function isServerAwake(): boolean {
  return awake;
}

/** The server answered (any status that came from the app itself). */
export function markServerAwake() {
  if (awake) return;
  awake = true;
  window.clearTimeout(slowTimer);
  emit();
}

export function requestStarted() {
  pending += 1;
  if (!awake && slowTimer === undefined) {
    slowTimer = window.setTimeout(() => {
      slow = true;
      emit();
    }, SLOW_AFTER_MS);
  }
}

export function requestFinished() {
  pending = Math.max(0, pending - 1);
  if (pending === 0) {
    window.clearTimeout(slowTimer);
    slowTimer = undefined;
    slow = false;
  }
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** True while a request is waiting on a server that hasn't answered yet. */
export function useServerWaking(): boolean {
  return useSyncExternalStore(subscribe, waking);
}
