/**
 * Loading and changing the signed-in user's contacts. Every change
 * refreshes the list (see useExpenses.ts for why the promise is returned).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCounterparty,
  listCounterparties,
  updateCounterparty,
  type CounterpartyInput,
} from "../lib/api";
import { BALANCES_KEY } from "./useBalances";

const COUNTERPARTIES_KEY = ["counterparties"];

export function useCounterparties() {
  return useQuery({
    queryKey: COUNTERPARTIES_KEY,
    queryFn: listCounterparties,
  });
}

// Returns a function that names a person: "You" for null, else the
// contact's name. Falls back to "Contact" while the list is loading.
export function usePersonName() {
  const contacts = useCounterparties();

  return (counterpartyId: number | null) =>
    counterpartyId === null
      ? "You"
      : (contacts.data?.find((contact) => contact.id === counterpartyId)?.name ?? "Contact");
}

export function useCreateCounterparty() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createCounterparty,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: COUNTERPARTIES_KEY }),
  });
}

export function useUpdateCounterparty() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: CounterpartyInput }) =>
      updateCounterparty(id, input),
    // Balances show contact names, so a rename refreshes them too.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: COUNTERPARTIES_KEY }),
        queryClient.invalidateQueries({ queryKey: BALANCES_KEY }),
      ]),
  });
}
