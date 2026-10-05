/**
 * People: your contacts, who owes whom, and money paid back, in one panel.
 * Shops and organizations are listed apart, under Merchants.
 *
 * Each contact shows their balance with you ("owes you ₹450"). People you
 * have a balance with come first, biggest first. "Settle up" records a
 * payment for the full balance; "Record a payment" records any amount.
 */

import { useState } from "react";

import { useMe } from "../hooks/useAuth";
import { useBalances, useCreateSettlement, useSettlements } from "../hooks/useBalances";
import { useCounterparties, useCreateCounterparty } from "../hooks/useCounterparties";
import { useDiscardGuard } from "../hooks/useDiscardGuard";
import { useToast } from "../hooks/useToast";
import type { Balance } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatMoney, todayISO } from "../lib/format";
import Button from "./Button";
import { Card, CardHeader } from "./Card";
import ContactForm from "./ContactForm";
import ExpectedList from "./ExpectedList";
import Modal from "./Modal";
import PersonRow from "./PersonRow";
import SettlementForm, { type SettlementDraft } from "./SettlementForm";
import SettlementRow from "./SettlementRow";
import SkeletonRows from "./SkeletonRows";

// Totals per currency, e.g. { INR: 450 } owed to you.
function totalsByCurrency(balances: Balance[], positive: boolean): [string, number][] {
  const totals = new Map<string, number>();

  for (const balance of balances) {
    const amount = Number(balance.amount);

    if (positive ? amount > 0 : amount < 0) {
      totals.set(balance.currency, (totals.get(balance.currency) ?? 0) + Math.abs(amount));
    }
  }

  return [...totals.entries()];
}

function Totals({ label, tone, totals }: { label: string; tone: string; totals: [string, number][] }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5">
      <p className="text-[11px] font-medium text-slate-500">{label}</p>
      {totals.length === 0 ? (
        <p className="mt-0.5 text-sm font-semibold text-slate-400">—</p>
      ) : (
        totals.map(([currency, amount]) => (
          <p key={currency} className={`mt-0.5 text-sm font-semibold tabular-nums ${tone}`}>
            {/* Display only: the server did the maths. */}
            {formatMoney(amount.toFixed(2), currency)}
          </p>
        ))
      )}
    </div>
  );
}

export default function PeoplePanel() {
  const me = useMe();
  const contacts = useCounterparties();
  const balances = useBalances();
  const settlements = useSettlements();
  const createContact = useCreateCounterparty();
  const createSettlement = useCreateSettlement();

  const toast = useToast();

  const [addingContact, setAddingContact] = useState(false);
  const [payment, setPayment] = useState<Partial<SettlementDraft> | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const contactGuard = useDiscardGuard(() => {
    createContact.reset();
    setAddingContact(false);
  });

  const paymentGuard = useDiscardGuard(() => {
    createSettlement.reset();
    setPayment(null);
  });

  const balanceList = balances.data ?? [];

  // Contacts with a balance first (biggest first), then the rest A–Z.
  const everyone = (contacts.data ?? [])
    .map((contact) => ({
      contact,
      balances: balanceList.filter((balance) => balance.counterparty_id === contact.id),
    }))
    .sort((a, b) => {
      const biggest = (entry: typeof a) =>
        Math.max(0, ...entry.balances.map((balance) => Math.abs(Number(balance.amount))));
      return biggest(b) - biggest(a);
    });
  const people = everyone.filter(({ contact }) => contact.counterparty_type === "PERSON");
  const merchants = everyone.filter(({ contact }) => contact.counterparty_type !== "PERSON");

  function settleUp(balance: Balance) {
    const theyOwe = !balance.amount.startsWith("-");

    setPayment({
      counterparty_id: String(balance.counterparty_id),
      direction: theyOwe ? "they_paid_me" : "i_paid_them",
      amount: balance.amount.replace("-", ""),
      currency: balance.currency,
    });
  }

  const settlementCount = settlements.data?.length ?? 0;

  return (
    <Card>
      <CardHeader
        title="People"
        subtitle="Tap someone to settle up or see what you share"
        action={
          <Button variant="secondary" size="sm" onClick={() => setAddingContact(true)}>
            + Add
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-2 px-5 pt-4">
        <Totals label="Owed to you" tone="text-emerald-600" totals={totalsByCurrency(balanceList, true)} />
        <Totals label="You owe" tone="text-amber-600" totals={totalsByCurrency(balanceList, false)} />
      </div>

      <div className="mt-3">
        {(contacts.isPending || balances.isPending) && <SkeletonRows rows={3} round />}

        {contacts.isError && (
          <p className="px-5 py-6 text-sm text-rose-700">{getErrorMessage(contacts.error)}</p>
        )}

        {contacts.isSuccess && everyone.length === 0 && (
          <div className="flex flex-col items-center gap-3 px-5 py-10 text-center">
            <p className="text-sm text-slate-500">
              No one here yet. Add the friends and places you spend with.
            </p>
            <Button variant="secondary" size="sm" onClick={() => setAddingContact(true)}>
              + Add a person
            </Button>
          </div>
        )}

        {!balances.isPending && people.length > 0 && (
          <ul className="divide-y divide-slate-100 border-t border-slate-100">
            {people.map(({ contact, balances: owed }) => (
              <PersonRow key={contact.id} contact={contact} balances={owed} onSettle={settleUp} />
            ))}
          </ul>
        )}

        {!balances.isPending && merchants.length > 0 && (
          <>
            <h3 className="border-t border-slate-100 px-5 pt-4 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Merchants
            </h3>
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {merchants.map(({ contact, balances: owed }) => (
                <PersonRow key={contact.id} contact={contact} balances={owed} onSettle={settleUp} />
              ))}
            </ul>
          </>
        )}
      </div>

      <ExpectedList />

      <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-3 py-2">
        <Button variant="ghost" size="sm" onClick={() => setPayment({})} disabled={everyone.length === 0}>
          Record a payment
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowHistory((shown) => !shown)}
          disabled={settlementCount === 0}
        >
          {showHistory ? "Hide history" : `History (${settlementCount})`}
        </Button>
      </div>

      {showHistory && settlementCount > 0 && (
        <ul className="divide-y divide-slate-100 border-t border-slate-100 bg-slate-50/50">
          {settlements.data?.map((settlement) => (
            <SettlementRow key={settlement.id} settlement={settlement} />
          ))}
        </ul>
      )}

      {addingContact && (
        <Modal
          title="Add a person or place"
          onClose={contactGuard.requestClose}
          discard={contactGuard.prompt}
        >
          <ContactForm
            initial={{ name: "", counterparty_type: "PERSON", relation: null }}
            submitLabel="Add"
            isSubmitting={createContact.isPending}
            error={createContact.error}
            onDirtyChange={contactGuard.setDirty}
            onSubmit={(values) =>
              createContact.mutate(values, {
                onSuccess: (contact) => {
                  contactGuard.close();
                  toast({ message: `Added ${contact.name}` });
                },
              })
            }
            onCancel={contactGuard.requestClose}
          />
        </Modal>
      )}

      {payment && (
        <Modal
          title={payment.counterparty_id ? "Settle up" : "Record a payment"}
          onClose={paymentGuard.requestClose}
          discard={paymentGuard.prompt}
        >
          <SettlementForm
            initial={{
              counterparty_id: "",
              direction: "they_paid_me",
              kind: "repayment",
              amount: "",
              currency: me.data?.default_currency ?? "INR",
              date: todayISO(),
              note: "",
              ...payment,
            }}
            isSubmitting={createSettlement.isPending}
            error={createSettlement.error}
            onDirtyChange={paymentGuard.setDirty}
            onSubmit={(values) =>
              createSettlement.mutate(values, {
                onSuccess: () => {
                  paymentGuard.close();
                  toast({ message: "Payment recorded" });
                },
              })
            }
            onCancel={paymentGuard.requestClose}
          />
        </Modal>
      )}
    </Card>
  );
}
