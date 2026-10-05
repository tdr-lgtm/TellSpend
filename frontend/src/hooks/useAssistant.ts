/**
 * The expense assistant: turn text into drafts, then save accepted ones.
 * Saving can create contacts as well as an expense or a settlement, so it
 * refreshes the expenses (with balances and the summary), the payments
 * and the contacts.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { clarifyExpenses, confirmDraft, confirmExpected, confirmRepayment, previewExpenses } from "../lib/api";
import type { ClarificationTurn, Decision, ExpenseDraft, RepaymentDraft } from "../lib/api";
import { useRefreshExpenses } from "./useExpenses";

export function usePreviewExpenses() {
  return useMutation({
    mutationFn: previewExpenses,
  });
}

// Answer a draft's questions; nothing is saved.
export function useClarify() {
  return useMutation({
    mutationFn: ({
      text,
      turns,
      decisions,
      focus,
    }: {
      text: string;
      turns: ClarificationTurn[];
      decisions: Decision[];
      focus?: string | null;
    }) => clarifyExpenses(text, turns, decisions, focus),
  });
}

export function useConfirmDraft() {
  const queryClient = useQueryClient();
  const refreshExpenses = useRefreshExpenses();

  return useMutation({
    mutationFn: ({ draft, settlementIds }: { draft: ExpenseDraft; settlementIds?: number[] }) =>
      confirmDraft(draft, settlementIds),
    onSuccess: () =>
      Promise.all([
        refreshExpenses(),
        queryClient.invalidateQueries({ queryKey: ["counterparties"] }),
        queryClient.invalidateQueries({ queryKey: ["settlements"] }),
      ]),
  });
}

export function useConfirmRepayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ repayment, expenseId }: { repayment: RepaymentDraft; expenseId?: number | null }) =>
      confirmRepayment(repayment, expenseId),
    onSuccess: () =>
      Promise.all(
        ["settlements", "balances", "summary", "counterparties", "expenses"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  });
}

export function useConfirmExpected() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: confirmExpected,
    onSuccess: () =>
      Promise.all(
        ["expected", "counterparties"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      ),
  });
}
