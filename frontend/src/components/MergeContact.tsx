/**
 * The same person saved under two names ("Aadhya" and "adhya"): merge the
 * other one into this contact, so every expense, share, item and payment
 * is theirs and balances aren't split.
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useCounterparties } from "../hooks/useCounterparties";
import { useToast } from "../hooks/useToast";
import { mergeCounterparty, type Counterparty } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import Button from "./Button";
import SelectField from "./SelectField";

export default function MergeContact({ contact, onDone }: { contact: Counterparty; onDone: () => void }) {
  const [other, setOther] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const contacts = useCounterparties();
  const queryClient = useQueryClient();
  const toast = useToast();

  const others = (contacts.data ?? []).filter((c) => c.id !== contact.id);
  if (others.length === 0) {
    return null;
  }
  const otherName = others.find((c) => String(c.id) === other)?.name;

  async function merge() {
    setBusy(true);
    setError(null);
    try {
      await mergeCounterparty(contact.id, Number(other));
      await Promise.all(
        ["counterparties", "expenses", "settlements", "balances", "summary"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] }),
        ),
      );
      toast({ message: `${otherName} is now part of ${contact.name}` });
      onDone();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-slate-100 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Same person?</p>
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <SelectField
            label={`Merge into ${contact.name}`}
            value={other}
            options={[
              { value: "", label: "Pick a contact" },
              ...others.map((c) => ({ value: String(c.id), label: c.name })),
            ]}
            onChange={(event) => setOther(event.target.value)}
          />
        </div>
        <Button size="sm" onClick={merge} disabled={!other || busy}>
          {busy ? "Merging…" : "Merge"}
        </Button>
      </div>
      {otherName && (
        <p className="mt-2 text-xs text-slate-500">
          Everything with {otherName} moves to {contact.name}, and {otherName} is removed.
        </p>
      )}
      {error != null && (
        <p role="alert" className="mt-2 text-xs text-rose-700">
          {getErrorMessage(error)}
        </p>
      )}
    </div>
  );
}
