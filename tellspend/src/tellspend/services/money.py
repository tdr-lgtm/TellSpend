"""
Exact money maths for balances (splitting a debt between creditors).

Everything works in whole paise so that splitting never loses or invents
a paisa: the parts always add up exactly to the total.
"""

from decimal import ROUND_DOWN, Decimal


PAISA = Decimal("0.01")


def to_paise(amount: Decimal) -> int:
    """
    Explanation:
        Turn an amount with at most 2 decimals into whole paise.

    Parameters:
        amount: e.g. Decimal("12.34").

    Returns:
        e.g. 1234.
    """
    return int((amount * 100).to_integral_value())


def from_paise(paise: int) -> Decimal:
    """
    Explanation:
        Turn whole paise back into an amount with 2 decimals.

    Parameters:
        paise: e.g. 1234.

    Returns:
        e.g. Decimal("12.34").
    """
    return (Decimal(paise) / 100).quantize(PAISA)


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """
    Explanation:
        Split `total` in proportion to `weights` so the parts add up
        EXACTLY to `total`. Each part first gets its rounded-down share;
        the leftover paise then go to the parts that lost the most to
        rounding (earlier parts win ties).

            allocate(100, [1, 1, 1]) -> [33.34, 33.33, 33.33]

    Parameters:
        total: The amount to split.
        weights: How much of it each part gets, relatively. Must add up
            to more than zero.

    Returns:
        One amount per weight, summing to `total`.
    """
    total_paise = to_paise(total)
    weight_sum = sum(weights, Decimal("0"))

    exact = [Decimal(total_paise) * weight / weight_sum for weight in weights]
    paise = [int(part.to_integral_value(rounding=ROUND_DOWN)) for part in exact]

    leftover = total_paise - sum(paise)
    by_rounding_loss = sorted(
        range(len(weights)),
        key=lambda index: (-(exact[index] - paise[index]), index),
    )

    for index in by_rounding_loss[:leftover]:
        paise[index] += 1

    return [from_paise(part) for part in paise]
