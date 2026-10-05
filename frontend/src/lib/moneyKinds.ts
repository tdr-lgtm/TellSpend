/**
 * What money between you and a contact was, in plain words. The same
 * wording everywhere (drafts, history, the form), so a loan never reads
 * as a repayment. Every kind but a gift moves the balance.
 */

export type MoneyKind = "repayment" | "loan" | "reimbursement" | "gift" | "balance";

export const MONEY_KINDS: { value: MoneyKind; label: string }[] = [
  { value: "repayment", label: "Paying back" },
  { value: "loan", label: "A loan" },
  { value: "reimbursement", label: "A reimbursement" },
  { value: "gift", label: "A gift (nothing owed)" },
  { value: "balance", label: "Already owed (no money moved)" },
];

// "You lent Parth", "Parth paid you back", "You gave Aadhya"...
export function describeMoney(kind: MoneyKind | null | undefined, fromMe: boolean, name: string): string {
  switch (kind) {
    case "loan":
      return fromMe ? `You lent ${name}` : `${name} lent you`;
    case "reimbursement":
      return fromMe ? `You reimbursed ${name}` : `${name} reimbursed you`;
    case "gift":
      return fromMe ? `You gave ${name}` : `${name} gave you`;
    // A debt that already existed: "from" is who is owed.
    case "balance":
      return fromMe ? `${name} owes you` : `You owe ${name}`;
    case "repayment":
      return fromMe ? `You paid ${name} back` : `${name} paid you back`;
    default:
      return fromMe ? `You sent ${name}` : `${name} sent you`;
  }
}

// The line under it: what it does to the balance.
export function kindNote(kind: MoneyKind | null | undefined): string {
  switch (kind) {
    case "loan":
      return "Loan · owed back";
    case "reimbursement":
      return "Reimbursement";
    case "gift":
      return "Gift · nothing owed";
    case "balance":
      return "Existing balance · no money moved";
    case "repayment":
      return "Repayment, not an expense";
    default:
      return "What was it for?";
  }
}

// Money expected, not yet moved: "Parth will pay you" / "You'll pay Aadhya".
export function expectedSentence(theyPayMe: boolean, name: string): string {
  return theyPayMe ? `${name} will pay you` : `You'll pay ${name}`;
}
