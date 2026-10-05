/**
 * The contact form, used for adding and editing. Relation is only asked
 * for people; any other type sends relation: null.
 */

import { useEffect, useRef, useState } from "react";

import type { CounterpartyInput, CounterpartyType } from "../lib/api";
import { CONTACT_TYPES } from "../lib/contacts";
import { getErrorMessage } from "../lib/errors";
import { errorBoxClass } from "../lib/styles";
import Button from "./Button";
import Field from "./Field";
import FormFooter from "./FormFooter";
import SelectField from "./SelectField";

type ContactFormProps = {
  initial: CounterpartyInput;
  submitLabel: string;
  isSubmitting: boolean;
  error: unknown;
  onSubmit: (values: CounterpartyInput) => void;
  onCancel?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  cancelLabel?: string;
};

export default function ContactForm({
  initial,
  submitLabel,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
  onDirtyChange,
  cancelLabel = "Cancel",
}: ContactFormProps) {
  const [name, setName] = useState(initial.name);
  const [type, setType] = useState<CounterpartyType>(initial.counterparty_type);
  const [relation, setRelation] = useState(initial.relation ?? "");

  const isPerson = type === "PERSON";

  // Unsaved changes: anything differs from how the form started.
  const snapshot = JSON.stringify([name, type, relation]);
  const startSnapshot = useRef(snapshot);

  useEffect(() => {
    onDirtyChange?.(snapshot !== startSnapshot.current);
  }, [snapshot, onDirtyChange]);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          name,
          counterparty_type: type,
          relation: isPerson ? relation : null,
        });
      }}
    >
      <Field
        label="Name"
        placeholder="Parth, Swiggy, Airtel…"
        required
        maxLength={255}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />

      <div className="grid grid-cols-2 gap-3">
        <SelectField
          label="Type"
          value={type}
          options={CONTACT_TYPES}
          onChange={(event) => setType(event.target.value as CounterpartyType)}
        />

        {isPerson && (
          <Field
            label="Relation (optional)"
            placeholder="flatmate, wife…"
            maxLength={50}
            value={relation}
            onChange={(event) => setRelation(event.target.value)}
          />
        )}
      </div>

      {error != null && (
        <p role="alert" className={errorBoxClass}>
          {getErrorMessage(error)}
        </p>
      )}

      <FormFooter>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : submitLabel}
        </Button>
      </FormFooter>
    </form>
  );
}
