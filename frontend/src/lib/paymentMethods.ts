/**
 * Payment methods and how they are shown. The keys match the backend's
 * payment_methods.py.
 */

export const PAYMENT_METHODS: { value: string; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "credit_card", label: "Credit card" },
  { value: "debit_card", label: "Debit card" },
  { value: "card", label: "Card" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "wallet", label: "Wallet" },
  { value: "other", label: "Other" },
];

export function paymentMethodLabel(method: string): string {
  return PAYMENT_METHODS.find((option) => option.value === method)?.label ?? method;
}
