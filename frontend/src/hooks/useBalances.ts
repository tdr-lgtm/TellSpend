/**
 * Balances (who owes whom) and settlements (money paid back).
 *
 * Balances are computed by the server from expenses and settlements, so
 * any change to either refreshes them (see useExpenses.ts too).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createSettlement,
  listBalances,
  listSettlements,
} from "../lib/api";
import { SUMMARY_KEY } from "./useSummary";

export const BALANCES_KEY = ["balances"];
export const SETTLEMENTS_KEY = ["settlements"];

export function useBalances() {
  return useQuery({
    queryKey: BALANCES_KEY,
    queryFn: listBalances,
  });
}

export function useSettlements() {
  return useQuery({
    queryKey: SETTLEMENTS_KEY,
    queryFn: listSettlements,
  });
}

function useRefreshSettlementsAndBalances() {
  const queryClient = useQueryClient();

  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: SETTLEMENTS_KEY }),
      queryClient.invalidateQueries({ queryKey: BALANCES_KEY }),
      // The summary shows what's owed, so it changes too.
      queryClient.invalidateQueries({ queryKey: SUMMARY_KEY }),
    ]);
}

export function useCreateSettlement() {
  const refresh = useRefreshSettlementsAndBalances();

  return useMutation({
    mutationFn: createSettlement,
    onSuccess: refresh,
  });
}
