/**
 * Charges: what a bill adds on top of the items (tax, service charge,
 * delivery, tips, fees). Kept apart from items, since nothing was bought.
 * The kinds match the server's list (tellspend/charges.py).
 */

import {
  adjustmentsTotalPaise,
  describeAdjustments,
  kindLabel,
  newAdjustmentRow,
  toAdjustments,
  type AdjustmentRow,
} from "./adjustments";
import type { Charge } from "./api";

export const CHARGE_KINDS = [
  { value: "tax", label: "Tax" },
  { value: "service_charge", label: "Service charge" },
  { value: "delivery", label: "Delivery" },
  { value: "packaging", label: "Packaging" },
  { value: "tip", label: "Tip" },
  { value: "fee", label: "Fee" },
  { value: "rounding", label: "Rounding" },
  { value: "other", label: "Other charge" },
] as const;

export function chargeKindLabel(kind: string): string {
  return kindLabel(CHARGE_KINDS, kind, "Charge");
}

export const describeCharges = describeAdjustments;
export const chargesTotalPaise = adjustmentsTotalPaise;

export type ChargeRow = AdjustmentRow;

export function newChargeRow(charge?: Charge): ChargeRow {
  return newAdjustmentRow(CHARGE_KINDS, charge);
}

export function toCharges(rows: ChargeRow[]): Charge[] | string {
  return toAdjustments(rows, CHARGE_KINDS);
}
