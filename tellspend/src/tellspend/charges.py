"""
The kinds of charge a bill can have on top of its items: taxes, service
charges, delivery, packaging, tips, fees and rounding.

Charges are never items (nothing was bought) and never discounts (they
make the bill bigger). One list, used by the database check, the API and
the assistant, so they can't disagree.
"""

from typing import Literal, get_args


ChargeKind = Literal[
    "tax",             # GST, CGST, SGST, VAT...
    "service_charge",
    "delivery",
    "packaging",
    "tip",
    "fee",             # convenience, platform, late or card fees
    "rounding",        # rounding up
    "other",
]

CHARGE_KINDS: tuple[str, ...] = get_args(ChargeKind)

# How each kind is shown when the bill didn't name it.
CHARGE_LABELS: dict[str, str] = {
    "tax": "Tax",
    "service_charge": "Service charge",
    "delivery": "Delivery",
    "packaging": "Packaging",
    "tip": "Tip",
    "fee": "Fee",
    "rounding": "Rounding",
    "other": "Other charge",
}

# Fail at import time if a kind is added without a label (or the reverse).
assert set(CHARGE_LABELS) == set(CHARGE_KINDS)


def charge_kind_check_sql(column: str = "kind") -> str:
    """
    Explanation:
        Build the SQL CHECK condition that limits a column to the known
        charge kinds.

    Parameters:
        column: The column name to check.

    Returns:
        SQL such as "kind IN ('tax', 'service_charge', ...)".
    """
    kinds = ", ".join(f"'{kind}'" for kind in CHARGE_KINDS)
    return f"{column} IN ({kinds})"
