/**
 * Contact types and how they are shown.
 */

import type { CounterpartyType } from "./api";

export const CONTACT_TYPES: { value: CounterpartyType; label: string }[] = [
  { value: "PERSON", label: "Person" },
  { value: "BUSINESS", label: "Business" },
  { value: "ORGANIZATION", label: "Organization" },
];

export function contactTypeLabel(type: CounterpartyType): string {
  return CONTACT_TYPES.find((option) => option.value === type)?.label ?? type;
}