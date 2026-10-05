/**
 * The monthly summary. It's computed from expenses and balances, so the
 * expense and settlement hooks refresh it after every change.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getSummary } from "../lib/api";

export const SUMMARY_KEY = ["summary"];

export function useSummary(month: string) {
  return useQuery({
    queryKey: [...SUMMARY_KEY, month],
    queryFn: () => getSummary(month),
    // While another month loads, keep showing the previous one.
    placeholderData: keepPreviousData,
  });
}
