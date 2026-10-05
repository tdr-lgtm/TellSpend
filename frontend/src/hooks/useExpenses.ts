/**
 * Loading and changing the signed-in user's expenses.
 *
 * Every change refreshes the list afterwards. Because the refresh promise
 * is returned from onSuccess/onSettled, the mutation stays "pending" until
 * the new list has arrived, so buttons show "Saving…" until the screen
 * is actually up to date. Balances and the monthly summary are worked
 * out from expenses, so they are refreshed too, and so are repayments
 * (deleting an expense can delete the ones saved as paying it back).
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createExpense,
  listExpenses,
  updateExpense,
  type ExpenseInput,
} from "../lib/api";
import { BALANCES_KEY, SETTLEMENTS_KEY } from "./useBalances";
import { SUMMARY_KEY } from "./useSummary";

const EXPENSES_KEY = ["expenses"];

export function useExpenses(category?: string) {
  return useQuery({
    queryKey: [...EXPENSES_KEY, category ?? "all"],
    queryFn: () => listExpenses(category),
    // While a new filter loads, keep showing the previous list.
    placeholderData: keepPreviousData,
  });
}

export function useRefreshExpenses() {
  const queryClient = useQueryClient();

  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: EXPENSES_KEY }),
      queryClient.invalidateQueries({ queryKey: BALANCES_KEY }),
      queryClient.invalidateQueries({ queryKey: SUMMARY_KEY }),
      queryClient.invalidateQueries({ queryKey: SETTLEMENTS_KEY }),
    ]);
}

export function useCreateExpense() {
  const refresh = useRefreshExpenses();

  return useMutation({
    mutationFn: createExpense,
    onSuccess: refresh,
  });
}

export function useUpdateExpense() {
  const refresh = useRefreshExpenses();

  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: ExpenseInput }) =>
      updateExpense(id, input),
    onSuccess: refresh,
  });
}
