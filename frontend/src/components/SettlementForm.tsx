/**
 * Record money between you and a contact: which way it went and what it
 * was (paying back, a loan, a reimbursement, a gift). Starts from
 * `initial`; the parent gives it a new `key` to reset or prefill it.
 */

import { useEffect, useRef, useState } from "react";

import { useCounterparties } from "../hooks/useCounterparties";
import type { SettlementDirection, SettlementInput } from "../lib/api";
import { getErrorMessage } from "../lib/errors";
import { formatMoney } from "../lib/format";
import { describeMoney, MONEY_KINDS } from "../lib/moneyKinds";
import { fromPaise, toPaise } from "../lib/money";
import { errorBoxClass } from "../lib/styles";
import Button from "./Button";
import Field from "./Field";
import FormFooter from "./FormFooter";
import SelectField from "./SelectField";

// The contact starts as "" (nobody picked yet); everything else as sent.
export type SettlementDraft = Omit<SettlementInput, "counterparty_id"> & {
  counterparty_id: string;
};

type SettlementFormProps = {
  initial: SettlementDraft;
  isSubmitting: boolean;
  error: unknown;
  onSubmit: (values: SettlementInput) => void;
  onCancel?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
};

const DIRECTIONS: { value: SettlementDirection; label: string }[] = [
  { value: "they_paid_me", label: "They paid me" },
  { value: "i_paid_them", label: "I paid them" },
];

// An existing debt moves no money, so the choice is who owes whom. It's
// stored as if the one owed had handed it over (see models.Settlement).
const OWED_DIRECTIONS: { value: SettlementDirection; label: string }[] = [
  { value: "i_paid_them", label: "They owe me" },
  { value: "they_paid_me", label: "I owe them" },
];

export default function SettlementForm({
  initial,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
  onDirtyChange,
}: SettlementFormProps) {
  const [values, setValues] = useState(initial);
  const [formError, setFormError] = useState<string | null>(null);
  const contacts = useCounterparties();

  // Unsaved changes: anything differs from how the form started.
  const snapshot = JSON.stringify(values);
  const startSnapshot = useRef(snapshot);

  useEffect(() => {
    onDirtyChange?.(snapshot !== startSnapshot.current);
  }, [snapshot, onDirtyChange]);

  // The payment in plain words, so the direction can't be misread.
  const contactName = contacts.data?.find((c) => String(c.id) === values.counterparty_id)?.name;
  const paise = toPaise(values.amount);
  const currency = values.currency.trim().toUpperCase();
  let sentence: string | null = null;

  if (contactName && paise && /^[A-Z]{3}$/.test(currency)) {
    const amount = formatMoney(fromPaise(paise), currency);
    sentence = `${describeMoney(values.kind, values.direction === "i_paid_them", contactName)} ${amount}`;
  }

  function update(field: keyof SettlementDraft, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit() {
    const paise = toPaise(values.amount);

    if (!values.counterparty_id) {
      setFormError("Pick who the money was between.");
      return;
    }

    if (!paise) {
      setFormError("Enter an amount like 450 or 99.50.");
      return;
    }

    setFormError(null);
    onSubmit({
      ...values,
      counterparty_id: Number(values.counterparty_id),
      amount: fromPaise(paise),
      currency: values.currency.trim().toUpperCase(),
    });
  }

  const message = formError ?? (error ? getErrorMessage(error) : null);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        handleSubmit();
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <SelectField
          label="Contact"
          value={values.counterparty_id}
          options={[
            { value: "", label: "Pick a contact" },
            ...(contacts.data ?? []).map((contact) => ({
              value: String(contact.id),
              label: contact.name,
            })),
          ]}
          onChange={(event) => update("counterparty_id", event.target.value)}
        />
        <SelectField
          label={values.kind === "balance" ? "Who owes" : "Direction"}
          value={values.direction}
          options={values.kind === "balance" ? OWED_DIRECTIONS : DIRECTIONS}
          onChange={(event) => update("direction", event.target.value)}
        />
      </div>

      <SelectField
        label="What was it"
        value={values.kind}
        options={MONEY_KINDS}
        onChange={(event) => update("kind", event.target.value)}
      />

      <div className="grid grid-cols-[1fr_6rem] gap-3">
        <Field
          label="Amount"
          inputMode="decimal"
          placeholder="450"
          required
          value={values.amount}
          onChange={(event) => update("amount", event.target.value)}
        />
        <Field
          label="Currency"
          required
          minLength={3}
          maxLength={3}
          value={values.currency}
          onChange={(event) => update("currency", event.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Date"
          type="date"
          required
          value={values.date}
          onChange={(event) => update("date", event.target.value)}
        />
        <Field
          label="Note (optional)"
          placeholder="UPI, cash…"
          maxLength={255}
          value={values.note}
          onChange={(event) => update("note", event.target.value)}
        />
      </div>

      {sentence && (
        <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-700">{sentence}</p>
      )}

      {message && (
        <p role="alert" className={errorBoxClass}>
          {message}
        </p>
      )}

      <FormFooter>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Record payment"}
        </Button>
      </FormFooter>
    </form>
  );
}
