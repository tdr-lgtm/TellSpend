/**
 * Turning an assistant draft into the expense form's starting values, for
 * "Edit first". The form only knows your contacts, so the people a draft
 * proposes are added as contacts first (withContacts), then every payment
 * and share goes into the form as the draft has it; nothing is dropped.
 */

import type { Counterparty, DraftPerson, ExpenseDraft, ExpenseInput } from "./api";

// The form's way of naming a person: null for you, else a contact id.
// Only a proposed new person has neither yet.
function formPerson(person: DraftPerson): number | null | undefined {
  if (person.kind === "me") {
    return null;
  }

  return person.kind === "contact" ? person.contact_id : undefined;
}

/**
 * The draft with its proposed people replaced by the contacts made for
 * them (by new_key), so it can go into the form whole.
 */
export function withContacts(draft: ExpenseDraft, created: Record<string, Counterparty>): ExpenseDraft {
  function resolve(person: DraftPerson): DraftPerson {
    const contact = person.kind === "new" && person.new_key ? created[person.new_key] : undefined;

    return contact
      ? { kind: "contact", contact_id: contact.id, new_key: null, name: contact.name }
      : person;
  }

  return {
    ...draft,
    paid_to: draft.paid_to ? resolve(draft.paid_to) : null,
    payments: draft.payments.map((payment) => ({ ...payment, person: resolve(payment.person) })),
    participants: draft.participants.map((share) => ({ ...share, person: resolve(share.person) })),
    refunds: draft.refunds.map((refund) => ({ ...refund, person: resolve(refund.person) })),
    new_contacts: draft.new_contacts.filter((contact) => !created[contact.key]),
  };
}

export function draftToInput(draft: ExpenseDraft, defaultCurrency: string): ExpenseInput {
  const everyone = [
    ...draft.payments.map((payment) => payment.person),
    ...draft.participants.map((share) => share.person),
    ...draft.refunds.map((refund) => refund.person),
  ];

  // Never true after withContacts; kept so a stray proposed person can't
  // end up in the form as "you".
  const peopleFit = everyone.every((person) => formPerson(person) !== undefined);

  const paidTo = draft.paid_to ? formPerson(draft.paid_to) : null;

  return {
    date: draft.date,
    amount: draft.amount ?? "",
    currency: draft.currency || defaultCurrency,
    description: draft.description ?? "",
    category: draft.category,
    counterparty_id: paidTo ?? null,
    payments: peopleFit
      ? draft.payments.map((payment) => ({
          counterparty_id: formPerson(payment.person) ?? null,
          amount: payment.amount,
          method: payment.method,
          provider: payment.provider,
        }))
      : [],
    participants: peopleFit
      ? draft.participants.map((share) => ({
          counterparty_id: formPerson(share.person) ?? null,
          share_amount: share.share_amount,
        }))
      : [],
    discount_amount: draft.discount_amount,
    // Each item with whose it is, as the draft had it.
    items: draft.items.map((item, index) => {
      const owners = (draft.item_owners[index] ?? []).map((owner) => ({
        counterparty_id: formPerson(owner.person),
        amount: owner.share_amount,
      }));
      return owners.every((owner) => owner.counterparty_id !== undefined)
        ? { ...item, owners: owners as { counterparty_id: number | null; amount: string }[] }
        : item;
    }),
    charges: draft.charges,
    deductions: draft.deductions,
    // What the assistant worked out stays with it.
    note: draft.notes.join(" ") || null,
    refunds: peopleFit
      ? draft.refunds.map((refund) => ({
          counterparty_id: formPerson(refund.person) ?? null,
          amount: refund.amount,
          label: refund.label,
          date: refund.date,
        }))
      : [],
  };
}
