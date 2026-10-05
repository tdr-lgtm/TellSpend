/**
 * A labelled text input, used by every form.
 */

import type { InputHTMLAttributes } from "react";

import { inputClass, labelClass } from "../lib/styles";

type FieldProps = {
  label: string;
} & InputHTMLAttributes<HTMLInputElement>;

export default function Field({ label, ...inputProps }: FieldProps) {
  return (
    <label className={labelClass}>
      {label}
      <input {...inputProps} className={inputClass} />
    </label>
  );
}
