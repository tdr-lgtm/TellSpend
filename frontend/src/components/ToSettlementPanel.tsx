/**
 * For an expense that wasn't a purchase (e.g. saved as "Repayment"): turn
 * it into the money between you and a contact that it really was. Same
 * amount, currency and date; it stops counting as spending.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useCounterparties } from "../hooks/useCounterparties";
import { useToast } from "../hooks/useToast";
import { expenseToSettlement, type Expense, type SettlementDirection } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { MONEY_KINDS, type MoneyKind } from "../lib/moneyKinds";
import Button from "./Button";
import SelectField from "./SelectField";

type ToSettlementPanelProps = {
  expense: Expense;
  onDone: () => void; // converted: close the expense
};

export default function ToSettlementPanel({ expense, onDone }: ToSettlementPanelProps) {
  const [open, setOpen] = useState(false);
  const [contact, setContact] = useState("");
  const [direction, setDirection] = useState<SettlementDirection>("i_paid_them");
  const [kind, setKind] = useState<MoneyKind>("repayment");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const contacts = useCounterparties();
  const queryClient = useQueryClient();
  const toast = useToast();

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mb-4 text-xs font-medium text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline"
      >
        Not a purchase? Record it as money between you and someone
      </button>
    );
  }

  async function convert() {
    if (!contact) {
      setError(new Error("Pick who the money was between."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await expenseToSettlement(expense.id, { counterparty_id: Number(contact), direction, kind });
      await Promise.all(
        ["expenses", "settlements", "balances", "summary"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
      toast({ message: "Recorded as money between people, not spending" });
      onDone();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 flex flex-col gap-3 rounded-2xl bg-slate-50 p-4">
      <p className="text-sm text-slate-700">Record this as money between you and someone instead of spending.</p>
      <div className="grid grid-cols-2 gap-3">
        <SelectField
          label="Who"
          value={contact}
          options={[
            { value: "", label: "Pick a contact" },
            ...(contacts.data ?? []).map((c) => ({ value: String(c.id), label: c.name })),
          ]}
          onChange={(event) => setContact(event.target.value)}
        />
        <SelectField
          label="Direction"
          value={direction}
          options={[
            { value: "i_paid_them", label: "I paid them" },
            { value: "they_paid_me", label: "They paid me" },
          ]}
          onChange={(event) => setDirection(event.target.value as SettlementDirection)}
        />
      </div>
      <SelectField
        label="What was it"
        value={kind}
        options={MONEY_KINDS}
        onChange={(event) => setKind(event.target.value as MoneyKind)}
      />
      {error != null && (
        <p role="alert" className="text-xs text-rose-700">
          {getErrorMessage(error)}
        </p>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={convert} disabled={busy}>
          {busy ? "Moving…" : "Move it"}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
