/**
 * Turns any error from an API call into one sentence to show the user.
 */

import axios from "axios";

export function getErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }

  // No response at all: server down, wrong address, or no internet.
  if (!error.response) {
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