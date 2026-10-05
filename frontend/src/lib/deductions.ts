/**
 * Deductions: what's taken off a bill's price before paying (discounts,
 * rounding down). Each kind stays its own line. Refunds are not deductions
 * (see lib/refunds.ts). The kinds match the server's list
 * (tellspend/deductions.py).
 */

import {
  adjustmentsTotalPaise,
  kindLabel,
  newAdjustmentRow,
  toAdjustments,
  type AdjustmentRow,
} from "./adjustments";
import type { Deduction } from "./api";

export const DEDUCTION_KINDS = [
  { value: "discount", label: "Discount" },
  { value: "rounding", label: "Rounding" },
  { value: "other", label: "Other deduction" },
] as const;

export function deductionKindLabel(kind: string): string {
  return kindLabel(DEDUCTION_KINDS, kind, "Deduction");
}

export const deductionsTotalPaise = adjustmentsTotalPaise;

export type DeductionRow = AdjustmentRow;

export function newDeductionRow(deduction?: Deduction): DeductionRow {
  return newAdjustmentRow(DEDUCTION_KINDS, deduction);
}

export function toDeductions(rows: DeductionRow[]): Deduction[] | string {
  return toAdjustments(rows, DEDUCTION_KINDS);
}
