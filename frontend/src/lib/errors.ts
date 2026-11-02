/**
 * Turns any error from an API call into one sentence to show the user.
 */

import axios from "axios";

import { isServerAwake } from "./serverWake";

export function getErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }

  // No response at all: still waking up, server down, or no internet.
  if (!error.response) {
    if (!isServerAwake()) {
      return "The server is still waking up (the free host sleeps when idle). Please try again in a moment.";
    }
    if (error.code === "ECONNABORTED") {
      return "The server took too long to answer. Please try again.";
    }
    return "Can't reach the server. Check your connection.";
  }

  const detail = error.response.data?.detail;

  // Our own errors: {"detail": "Incorrect email or password."}
  if (typeof detail === "string") {
    return detail;
  }

  // Validation errors (422): {"detail": [{"loc": [..., "email"], "msg": "..."}]}
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    const field = first.loc?.at(-1);
    const message = String(first.msg ?? "").replace(/^Value error, /, "");

    // A rule about the whole request (e.g. "Payments add up to...") is
    // reported on "body", and a list entry on its index: no field name.
    const hasFieldName = typeof field === "string" && field !== "body";

    return hasFieldName ? `${field}: ${message}` : message;
  }

  return fallback;
}