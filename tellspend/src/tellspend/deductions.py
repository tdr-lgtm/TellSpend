from typing import Literal, get_args

DeductionKind = Literal[
    "discount", # discounts, coupons, offers, cashback on the bill
    "rounding", # rounding down
    "other"
]

DEDUCTION_KINDS: tuple[str, ...] = get_args(DeductionKind)

# How each kind is shown when the bill didn't name it.
DEDUCTION_LABELS: dict[str, str] = {
    "discount": "Discount",
    "rounding": "Rounding",
    "other": "Other deduction",
}

# Fail at import time if a kind is added without a label (or the reverse).
assert set(DEDUCTION_LABELS) == set(DEDUCTION_KINDS)

def deduction_kind_check_sql(column: str = "kind") -> str:
    """
    Explanation:
        Build the SQL CHECK condition that limits a column to the known
        deduction kinds.

    Parameters:
        column: The column name to check.

    Returns:
        SQL such as "kind IN ('discount', 'refund', ...)".
    """
    kinds = ", ".join(f"'{kind}'" for kind in DEDUCTION_KINDS)
    return f"{column} IN ({kinds})"
