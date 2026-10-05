from typing import Literal, get_args

PaymentMethod = Literal[
    "cash",
    "upi",
    "credit_card",
    "debit_card",
    "card", # a card, when credit/debit isn't said
    "bank_transfer",
    "wallet",
    "other",
]

PAYMENT_METHODS: tuple[str, ...] = get_args(PaymentMethod)

def payment_method_check_sql(column: str = "method") -> str:
    """
    Explanation:
        Build the SQL CHECK condition that limits a column to the known
        payment methods (or NULL: method not given).

    Parameters:
        column: The column name to check.

    Returns:
        SQL such as "method IS NULL OR method IN ('cash', 'upi', ...)".
    """
    methods = ", ".join(f"'{method}'" for method in PAYMENT_METHODS)
    return f"{column} IS NULL OR {column} IN ({methods})"
