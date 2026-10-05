/**
 * One payment in the People panel's history. Delete is instant, with an
 * Undo toast that records the same payment again.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { usePersonName } from "../hooks/useCounterparties";
import { useToast } from "../hooks/useToast";
import { createSettlement, deleteSettlement, updateSettlement, type Settlement } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatDate, formatMoney } from "../lib/format";
import { describeMoney } from "../lib/moneyKinds";
import Avatar from "./Avatar";
import Modal from "./Modal";
import SettlementForm from "./SettlementForm";

export default function SettlementRow({ settlement }: { settlement: Settlement }) {
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const queryClient = useQueryClient();
  const personName = usePersonName();
  const toast = useToast();

  const name = personName(settlement.counterparty_id);
  const summary = describeMoney(settlement.kind, settlement.direction === "i_paid_them", name);

  // Payments change balances and the monthly summary too.
  const refresh = () =>
    Promise.all(
      ["settlements", "balances", "summary"].map((key) =>
        queryClient.invalidateQueries({ queryKey: [key] }),
      ),
    );

  async function remove() {
    const saved = {
      counterparty_id: settlement.counterparty_id,
      direction: settlement.direction,
      kind: settlement.kind,
      amount: settlement.amount,
      currency: settlement.currency,
      date: settlement.date,
      note: settlement.note ?? "",
    };

    setDeleting(true);

    try {
      await deleteSettlement(settlement.id);
    } catch (error) {
      toast({ message: getErrorMessage(error), tone: "error" });
      setDeleting(false);
      return;
    }

    toast({
      message: "Payment deleted",
      action: {
        label: "Undo",
        onClick: async () => {
          try {
            await createSettlement(saved);
            await refresh();
            toast({ message: "Payment restored" });
          } catch (error) {
            toast({ message: getErrorMessage(error), tone: "error" });
          }
        },
      },
    });
    await refresh();
  }

  return (
    <li className="flex items-center gap-3 px-5 py-2.5">
      <Avatar name={name} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-slate-800">{summary}</p>
        <p className="truncate text-[11px] text-slate-400">
          {formatDate(settlement.date)}
          {settlement.note && ` · ${settlement.note}`}
        </p>
      </div>
      <p className="shrink-0 text-xs font-semibold tabular-nums text-slate-700">
        {formatMoney(settlement.amount, settlement.currency)}
      </p>
      <button
        type="button"
        aria-label={`Edit: ${summary}`}
        title="Edit"
        onClick={() => setEditing(true)}
        className="flex h-7 shrink-0 items-center justify-center rounded-lg px-1.5 text-[11px] font-medium text-slate-400 hover:bg-white hover:text-slate-900"
      >
        Edit
      </button>
      <button
        type="button"
        aria-label={`Delete payment: ${summary}`}
        title="Delete payment"
        onClick={remove}
        disabled={deleting}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-base leading-none text-slate-300 hover:bg-white hover:text-rose-600 disabled:opacity-40"
      >
        ×
      </button>

      {editing && (
        <Modal title="Edit" onClose={() => setEditing(false)}>
          <SettlementForm
            initial={{
              counterparty_id: String(settlement.counterparty_id),
              direction: settlement.direction,
              kind: settlement.kind,
              amount: settlement.amount,
              currency: settlement.currency,
              date: settlement.date,
              note: settlement.note ?? "",
            }}
            isSubmitting={saving}
            error={saveError}
            onSubmit={async (values) => {
              setSaving(true);
              setSaveError(null);
              try {
                await updateSettlement(settlement.id, values);
                await refresh();
                setEditing(false);
                toast({ message: "Changes saved" });
              } catch (error) {
                setSaveError(error);
              } finally {
                setSaving(false);
              }
            }}
            onCancel={() => setEditing(false)}
          />
        </Modal>
      )}
    </li>
  );
}
