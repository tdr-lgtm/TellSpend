/**
 * The fixed category list from the API, fetched once per session.
 */

import { useQuery } from "@tanstack/react-query";
import { listCategories } from "../lib/api";

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: listCategories,
    // The list only changes when the server is redeployed.
    staleTime: Infinity,
  });
}

// Returns a function that turns a key ("food_dining") into its label
// ("Food & dining"). Falls back to the key while the list is loading.
export function useCategoryLabel() {
  const categories = useCategories();

  return (key: string) =>
    categories.data?.find((category) => category.key === key)?.label ?? key;
}