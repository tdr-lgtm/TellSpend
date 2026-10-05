/**
 * A labelled dropdown, styled like Field. Without a label it's just the
 * dropdown (give it an aria-label then), e.g. for filters.
 */

import type { SelectHTMLAttributes } from "react";

import { inputClass, labelClass } from "../lib/styles";

type Option = {
  value: string;
  label: string;
};

type SelectFieldProps = {
  label?: string;
  options: Option[];
} & SelectHTMLAttributes<HTMLSelectElement>;

export default function SelectField({ label, options, className = "", ...selectProps }: SelectFieldProps) {
  const select = (
    <select {...selectProps} className={`${inputClass} ${className}`}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );

  if (!label) {
    return select;
  }

  return (
    <label className={labelClass}>
      {label}
      {select}
    </label>
  );
}
