/**
 * Money you're expecting that hasn't moved yet. Marking one as happened
 * records a payment, so balances, payments and the summary refresh.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteExpected, listExpected, markExpectedDone } from "../lib/api";

export function useExpected() {
  return useQuery({ queryKey: ["expected"], queryFn: listExpected });
}

export function useMarkExpectedDone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, date, amount }: { id: number; date: string; amount?: string }) =>
      markExpectedDone(id, date, amount),
    onSuccess: () =>
      Promise.all(
        ["expected", "settlements", "balances", "summary"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  });
}

export function useDeleteExpected() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteExpected,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["expected"] }),
  });
}
