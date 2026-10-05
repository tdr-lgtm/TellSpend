from typing import Literal, get_args

Category = Literal[
    "food_dining",
    "groceries",
    "transport",
    "shopping",
    "bills_utilities",
    "rent_housing",
    "entertainment",
    "travel",
    "health",
    "education",
    "personal_care",
    "gifts_donations",
    "other",
]

CATEGORY_KEYS: tuple[str, ...] = get_args(Category)

# Human-friendly names shown in the UI.
CATEGORY_LABELS: dict[str, str] = {
    "food_dining": "Food & dining",
    "groceries": "Groceries",
    "transport": "Transport",
    "shopping": "Shopping",
    "bills_utilities": "Bills & utilities",
    "rent_housing": "Rent & housing",
    "entertainment": "Entertainment",
    "travel": "Travel",
    "health": "Health",
    "education": "Education",
    "personal_care": "Personal care",
    "gifts_donations": "Gifts & donations",
    "other": "Other",
}

# Fail at import time if a category is added without a label (or the reverse).
assert set(CATEGORY_LABELS) == set(CATEGORY_KEYS)

DEFAULT_CATEGORY = "other"

def category_check_sql(column: str = "category") -> str:
    """
    Explanation:
        Build the SQL CHECK condition that limits a column to the known
        categories, so the database rejects any value outside this list.

    Parameters:
        column: The column name to check.

    Returns:
        SQL such as "category IN ('food_dining', 'groceries', ...)".
    """
    keys = ", ".join(f"'{key}'" for key in CATEGORY_KEYS)
    return f"{column} IN ({keys})"
