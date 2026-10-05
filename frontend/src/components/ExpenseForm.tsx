/**
 * The expense form, used for adding and editing.
 *
 * It keeps its own field values, starting from `initial`. To clear it,
 * the parent gives it a new `key`, which makes React start it fresh.
 *
 * "Paid by" and "Split between" are lists of people. With one person,
 * they paid (or owe) the whole amount; with several, each needs an amount
 * and the amounts must add up. All money maths is done in whole paise.
 *
 * "More details" holds the bill's items, its deductions (discounts,
 * rounding down) and its charges (tax, fees, tips), each line of its own
 * kind and kept apart. The amount is always what was charged, so when
 * items are listed, items - deductions + charges must equal the amount.
 *
 * Refunds are money given back after paying, each to someone who paid.
 * The amount and payments stay as paid; the split is of what's left.
 */

import { useEffect, useRef, useState } from "react";

import { useCategories } from "../hooks/useCategories";
import { useCounterparties } from "../hooks/useCounterparties";
import type { ExpenseInput } from "../lib/api";
import { CHARGE_KINDS, chargesTotalPaise, newChargeRow, toCharges } from "../lib/charges";
import {
  DEDUCTION_KINDS,
  deductionsTotalPaise,
  newDeductionRow,
  toDeductions,
} from "../lib/deductions";
import { getErrorMessage } from "../lib/errors";
import { newItemRow, toItems } from "../lib/items";
import { fromPaise, toPaise } from "../lib/money";
import { ME, idFromPerson, rowAmounts, rowsFrom } from "../lib/people";
import { newRefundRow, refundsTotalPaise, toRefunds } from "../lib/refunds";
import { errorBoxClass } from "../lib/styles";
import AdjustmentRows from "./AdjustmentRows";
import Button from "./Button";
import Field from "./Field";
import FormFooter from "./FormFooter";
import ItemRows from "./ItemRows";
import PeopleRows from "./PeopleRows";
import RefundRows from "./RefundRows";
import SelectField from "./SelectField";

// The plain text fields; people are kept separately as rows.
type TextFields = Pick<ExpenseInput, "date" | "amount" | "currency" | "description" | "category">;

type ExpenseFormProps = {
  initial: ExpenseInput;
  submitLabel: string;
  isSubmitting: boolean;
  error: unknown;
  onSubmit: (values: ExpenseInput) => void;
  onCancel?: () => void;
  // Told whenever the form gains or loses unsaved changes.
  onDirtyChange?: (dirty: boolean) => void;
  // Editing only: shows a Delete button in the footer.
  onDelete?: () => void;
  isDeleting?: boolean;
  // Shown above the form: what's still unclear (a draft's questions),
  // or what saving won't change (repayments linked to it).
  warnings?: string[];
};

// Anyone other than you involved, or payment details given? Then the
// people section starts open.
function hasPeopleDetails(input: ExpenseInput): boolean {
  return (
    input.payments.length > 1 ||
    input.payments.some((payment) => payment.counterparty_id !== null || payment.method) ||
    input.participants.some((share) => share.counterparty_id !== null)
  );
}

export default function ExpenseForm({
  initial,
  submitLabel,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
  onDirtyChange,
  onDelete,
  isDeleting = false,
  warnings = [],
}: ExpenseFormProps) {
  const [values, setValues] = useState<TextFields>({
    date: initial.date,
    amount: initial.amount,
    currency: initial.currency,
    description: initial.description,
    category: initial.category,
  });
  const [paidTo, setPaidTo] = useState(
    initial.counterparty_id === null ? "" : String(initial.counterparty_id),
  );
  const [payers, setPayers] = useState(() => rowsFrom(initial.payments));
  const [sharers, setSharers] = useState(() =>
    rowsFrom(
      initial.participants.map((share) => ({
        counterparty_id: share.counterparty_id,
        amount: share.share_amount,
      })),
    ),
  );
  const [showPeople, setShowPeople] = useState(() => hasPeopleDetails(initial));
  const [itemRows, setItemRows] = useState(() => initial.items.map((item) => newItemRow(item)));
  const [deductionRows, setDeductionRows] = useState(() =>
    initial.deductions.map((deduction) => newDeductionRow(deduction)),
  );
  const [chargeRows, setChargeRows] = useState(() => initial.charges.map((charge) => newChargeRow(charge)));
  const [refundRows, setRefundRows] = useState(() => initial.refunds.map((refund) => newRefundRow(refund)));
  const [showDetails, setShowDetails] = useState(
    () =>
      initial.items.length > 0 ||
      initial.charges.length > 0 ||
      initial.deductions.length > 0 ||
      initial.refunds.length > 0,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [note, setNote] = useState(initial.note ?? "");

  const categories = useCategories();
  const contacts = useCounterparties();

  const categoryOptions = (categories.data ?? []).map((category) => ({
    value: category.key,
    label: category.label,
  }));
  const contactOptions = (contacts.data ?? []).map((contact) => ({
    value: String(contact.id),
    label: contact.name,
  }));
  const people = [{ value: ME, label: "You" }, ...contactOptions];

  const totalPaise = toPaise(values.amount);
  const deductedPaise = deductionsTotalPaise(deductionRows);
  // The split is of what's left after refunds.
  const refundedPaise = refundsTotalPaise(refundRows);
  const sharedPaise = totalPaise === null ? null : totalPaise - refundedPaise;
  const currency = values.currency.trim().toUpperCase();

  // Everything the user can change, without the rows' React keys. When it
  // differs from how the form started, there are unsaved changes.
  const snapshot = JSON.stringify({
    values,
    paidTo,
    payers: payers.map(({ person, amount, method, provider }) => [person, amount, method, provider]),
    sharers: sharers.map(({ person, amount }) => [person, amount]),
    items: itemRows.map(({ name, quantity, unit, amount }) => [name, quantity, unit, amount]),
    charges: chargeRows.map(({ kind, label, amount }) => [kind, label, amount]),
    deductions: deductionRows.map(({ kind, label, amount }) => [kind, label, amount]),
    refunds: refundRows.map(({ person, label, amount }) => [person, label, amount]),
    note,
  });
  const startSnapshot = useRef(snapshot);

  useEffect(() => {
    onDirtyChange?.(snapshot !== startSnapshot.current);
  }, [snapshot, onDirtyChange]);

  function update(field: keyof TextFields, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function handleSubmit() {
    if (!totalPaise) {
      setFormError("Enter an amount like 350 or 99.50.");
      return;
    }

    const paid = rowAmounts(payers, totalPaise, "Paid by");
    if (typeof paid === "string") {
      setFormError(paid);
      return;
    }

    const refunds = toRefunds(refundRows);
    if (typeof refunds === "string") {
      setFormError(refunds);
      return;
    }

    // A refund gives back part of what was paid, to someone who paid.
    const refundedTotal = refundsTotalPaise(refunds);
    if (refundedTotal >= totalPaise) {
      setFormError("The refunds are all of the amount or more.");
      return;
    }
    const payerPeople = new Set(payers.map((row) => row.person));
    if (refundRows.some((row) => !payerPeople.has(row.person))) {
      setFormError("A refund goes back to someone who paid.");
      return;
    }

    const shares = rowAmounts(sharers, totalPaise - refundedTotal, "Split between");
    if (typeof shares === "string") {
      setFormError(shares);
      return;
    }

    const items = toItems(itemRows);
    if (typeof items === "string") {
      setFormError(items);
      return;
    }

    // Whoever an item belongs to has a share of the cost.
    const sharerIds = new Set(sharers.map((row) => idFromPerson(row.person)));
    if (
      refunds.length === 0 &&
      items.some((item) => (item.owners ?? []).some((owner) => !sharerIds.has(owner.counterparty_id)))
    ) {
      setFormError("Someone an item belongs to has no share. Add them to the split, or change whose the item is.");
      return;
    }

    const charges = toCharges(chargeRows);
    if (typeof charges === "string") {
      setFormError(charges);
      return;
    }

    const deductions = toDeductions(deductionRows);
    if (typeof deductions === "string") {
      setFormError(deductions);
      return;
    }

    // The bill: items - deductions + charges = amount.
    const addedPaise = chargesTotalPaise(charges);
    const discountPaise = deductionsTotalPaise(deductions);

    if (items.length > 0) {
      const itemsPaise = items.reduce((total, item) => total + (toPaise(item.amount) ?? 0), 0);
      const billPaise = itemsPaise - discountPaise + addedPaise;

      if (billPaise !== totalPaise) {
        const steps = [
          `Items add up to ${fromPaise(itemsPaise)}`,
          discountPaise ? `less ${fromPaise(discountPaise)} in deductions` : "",
          addedPaise ? `plus ${fromPaise(addedPaise)} in tax and charges` : "",
        ].filter(Boolean);
        setFormError(
          steps.join(", ") +
            (steps.length > 1 ? `, that's ${fromPaise(billPaise)},` : "") +
            ` but the amount is ${fromPaise(totalPaise)}.`,
        );
        return;
      }
    } else if (addedPaise >= totalPaise + discountPaise) {
      setFormError(
        `Tax and charges add up to ${fromPaise(addedPaise)}, which leaves nothing for what was bought.`,
      );
      return;
    }

    setFormError(null);
    onSubmit({
      ...values,
      amount: fromPaise(totalPaise),
      currency,
      counterparty_id: paidTo ? Number(paidTo) : null,
      discount_amount: fromPaise(discountPaise),
      items,
      charges,
      deductions,
      refunds,
      note: note.trim() || null,
      payments: payers.map((row, index) => ({
        counterparty_id: idFromPerson(row.person),
        amount: fromPaise(paid[index]),
        method: row.method || null,
        provider: row.provider.trim() || null,
      })),
      participants: sharers.map((row, index) => ({
        counterparty_id: idFromPerson(row.person),
        share_amount: fromPaise(shares[index]),
      })),
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
      {warnings.length > 0 && (
        <ul className="space-y-1 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {warnings.map((warning) => (
            <li key={warning} className="flex gap-2">
              <span aria-hidden="true">!</span>
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-[1fr_6rem] gap-3">
        <Field
          label="Amount"
          inputMode="decimal"
          placeholder="0.00"
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
        <SelectField
          label="Category"
          value={values.category}
          options={categoryOptions}
          disabled={!categories.data}
          onChange={(event) => update("category", event.target.value)}
        />
      </div>

      <Field
        label="Description"
        placeholder="Lunch at Truffles"
        maxLength={255}
        value={values.description}
        onChange={(event) => update("description", event.target.value)}
      />

      <Field
        label="Note (optional)"
        placeholder="An estimate, repeats monthly…"
        maxLength={500}
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />

      <SelectField
        label="Paid to (optional)"
        value={paidTo}
        options={[{ value: "", label: "Not set" }, ...contactOptions]}
        onChange={(event) => setPaidTo(event.target.value)}
      />

      {(!showPeople || !showDetails) && (
        <div className="flex flex-wrap gap-2">
          {!showPeople && (
            <Button variant="secondary" size="sm" onClick={() => setShowPeople(true)}>
              + Split or someone else paid
            </Button>
          )}
          {!showDetails && (
            <Button variant="secondary" size="sm" onClick={() => setShowDetails(true)}>
              + Items, discounts, tax or refunds
            </Button>
          )}
        </div>
      )}

      {showPeople && (
        <div className="flex flex-col gap-5 rounded-2xl border border-slate-100 bg-slate-50/70 p-4">
          {contactOptions.length === 0 && (
            <p className="text-xs text-slate-500">
              Add people in the People panel to split expenses with them.
            </p>
          )}

          <PeopleRows
            legend="Paid by"
            wholeLabel="paid it all"
            rows={payers}
            onChange={setPayers}
            people={people}
            totalPaise={totalPaise}
            currency={currency}
            forPayments
          />

          <PeopleRows
            legend="Split between"
            wholeLabel="owes it all"
            rows={sharers}
            onChange={setSharers}
            people={people}
            totalPaise={sharedPaise}
            currency={currency}
            canSplitEqually
          />
        </div>
      )}

      {showDetails && (
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-100 bg-slate-50/70 p-4">
          <ItemRows
            rows={itemRows}
            onChange={setItemRows}
            amountPaise={totalPaise}
            discountPaise={deductedPaise}
            chargesPaise={chargesTotalPaise(chargeRows)}
            currency={currency}
            onUseAsAmount={(amount) => update("amount", amount)}
          />

          <AdjustmentRows
            rows={deductionRows}
            onChange={setDeductionRows}
            kinds={DEDUCTION_KINDS}
            legend="Discounts (optional)"
            noun="deduction"
            addLabel="+ Add discount or rounding"
          />
          {deductedPaise > 0 && totalPaise !== null && (
            <p className="-mt-2 text-xs text-slate-500">
              Price before these: {fromPaise(totalPaise + deductedPaise)} {currency}
            </p>
          )}

          <AdjustmentRows
            rows={chargeRows}
            onChange={setChargeRows}
            kinds={CHARGE_KINDS}
            legend="Tax & charges (optional)"
            noun="charge"
            addLabel="+ Add tax or charge"
          />

          <RefundRows
            rows={refundRows}
            onChange={setRefundRows}
            people={people.filter((option) => payers.some((row) => row.person === option.value))}
          />
          {refundedPaise > 0 && sharedPaise !== null && (
            <p className="-mt-2 text-xs text-slate-500">
              The split is of what's left after refunds: {fromPaise(sharedPaise)} {currency}
            </p>
          )}
        </div>
      )}

      {message && (
        <p role="alert" className={errorBoxClass}>
          {message}
        </p>
      )}

      <FormFooter
        start={
          onDelete && (
            <Button variant="danger" onClick={onDelete} disabled={isDeleting || isSubmitting}>
              {isDeleting ? "Deleting…" : "Delete"}
            </Button>
          )
        }
      >
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting || isDeleting}>
          {isSubmitting ? "Saving…" : submitLabel}
        </Button>
      </FormFooter>
    </form>
  );
}
