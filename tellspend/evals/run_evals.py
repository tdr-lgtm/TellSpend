"""
Run the evaluation set (evals/cases.py) through the real model and the
builder, and report every difference from the expected result.

    uv run python evals/run_evals.py            # every case
    uv run python evals/run_evals.py repay      # only cases whose text contains "repay"
"""

import datetime as dt
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cases import CASES, CONTACTS  # noqa: E402

from pydantic import ValidationError  # noqa: E402

from tellspend.api.schemas import ExpenseCreate  # noqa: E402
from tellspend.database.models import Counterparty, User  # noqa: E402
from tellspend.ingestion.builder import build_result  # noqa: E402
from tellspend.ingestion.extractor import AssistantUnavailable, extract  # noqa: E402

USER = User(id=1, name="xyz", default_currency="INR")

CONTACT_ROWS = [
    Counterparty(id=index + 1, name=name, counterparty_type=kind, relation=relation)
    for index, (name, kind, relation) in enumerate(CONTACTS)
]


def by_person(rows, amount_of) -> dict[str, str]:
    """person name -> total amount, from payment or share rows."""
    totals: dict[str, float] = {}
    for row in rows:
        totals[row.person.name] = totals.get(row.person.name, 0) + float(amount_of(row))
    return {name: f"{value:.2f}" for name, value in totals.items()}


def check(case: dict) -> tuple[bool, list[str], float]:
    """Run one case; return (passed, differences, seconds)."""
    text = case["text"]
    start = time.time()

    try:
        extraction = extract(text, dt.date.today(), USER.name)
    except AssistantUnavailable as error:
        return False, [f"model unavailable: {error.user_message}"], time.time() - start

    try:
        result = build_result(extraction, text, USER, CONTACT_ROWS, dt.date.today())
    except Exception as error:  # a crash is a failure to report, not to stop on
        return False, [f"CRASH {type(error).__name__}: {error}"], time.time() - start
    seconds = time.time() - start
    differences: list[str] = []

    all_problems = (
        [p for d in result.expenses for p in d.problems]
        + [p for r in result.repayments for p in r.problems]
        + result.skipped
    )

    if case.get("problem"):
        if not all_problems:
            differences.append("expected a problem, got none")
        return not differences, differences, seconds

    # Text that can honestly be read two ways: asking which is right too.
    if case.get("may_ask") and all_problems and not result.skipped:
        return True, [], seconds

    if all_problems:
        differences.append(f"unexpected problems: {all_problems}")

    expected = case.get("expenses", [])
    if len(result.expenses) != len(expected):
        differences.append(
            f"expected {len(expected)} expense(s), got {len(result.expenses)}: "
            f"{[str(d.amount) for d in result.expenses]}"
        )

    for want, draft in zip(expected, result.expenses):
        if str(draft.amount) != want["amount"]:
            differences.append(f"amount {draft.amount}, want {want['amount']} ({draft.notes})")
        if "currency" in want and draft.currency != want["currency"]:
            differences.append(f"currency {draft.currency}, want {want['currency']}")
        if "paid" in want:
            got = by_person(draft.payments, lambda p: p.amount)
            if got != want["paid"]:
                differences.append(f"paid {got}, want {want['paid']}")
        refunded = sum(float(r.amount) for r in draft.refunds)
        shares = want.get("shares", {"You": f"{float(want['amount']) - refunded:.2f}"})
        if "refunds" in want:
            got_refunds = sorted(str(r.amount) for r in draft.refunds)
            if got_refunds != sorted(want["refunds"]):
                differences.append(f"refunds {got_refunds}, want {sorted(want['refunds'])}")
        got = by_person(draft.participants, lambda s: s.share_amount)
        if got != shares:
            differences.append(f"shares {got}, want {shares}")

        # Taxes, fees, discounts, refunds... each kept as its own kind,
        # never as items (a charge listed as an item shows up here as a
        # missing charge).
        for what, lines in (("charges", draft.charges), ("deductions", draft.deductions)):
            if what in want:
                got_kinds = sorted(line.kind for line in lines)
                if got_kinds != sorted(want[what]):
                    differences.append(f"{what} {got_kinds}, want {sorted(want[what])}")

        # For every case: the draft saves.
        if not draft.problems:
            try:
                ExpenseCreate(
                    date=draft.date,
                    amount=draft.amount,
                    discount_amount=draft.discount_amount,
                    items=draft.items,
                    charges=draft.charges,
                    deductions=draft.deductions,
                    refunds=[{"amount": r.amount} for r in draft.refunds],
                    payments=[{"amount": p.amount} for p in draft.payments],
                    participants=[
                        {"counterparty_id": index, "share_amount": s.share_amount}
                        for index, s in enumerate(draft.participants)
                    ],
                )
            except ValidationError as error:
                differences.append(f"wouldn't save: {error.errors()[0]['msg']}")

    want_repayments = sorted(case.get("repayments", []))
    got_repayments = sorted(
        (r.from_person.name, r.to_person.name, str(r.amount)) for r in result.repayments
    )
    if got_repayments != want_repayments:
        differences.append(f"repayments {got_repayments}, want {want_repayments}")

    return not differences, differences, seconds


def main() -> None:
    wanted = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    cases = [case for case in CASES if wanted in case["text"].lower()]

    # A few at a time: faster, and still gentle on the provider.
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(check, cases))

    passed = 0
    for case, (ok, differences, seconds) in zip(cases, outcomes):
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {seconds:5.1f}s  {case['text']}")
        for difference in differences:
            print(f"        {difference}")

    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
