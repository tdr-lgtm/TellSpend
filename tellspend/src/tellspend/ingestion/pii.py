"""
Personal data the model doesn't need, kept from it: email addresses, UPI
IDs, card numbers, Aadhaar and PAN numbers, phone numbers and long account
numbers are replaced by placeholders ("[CARD_1]") before the text is sent
to the model, and put back into what the model answers, so the rest of
the pipeline (evidence checks, drafts, what's saved) sees exactly what
the user typed.

Only identifiers are masked. People's names stay: who paid and who owes
is what the model is asked to read. Amounts never look like any of these
(they're short, or written with commas: "1,20,000"), and if a long number
ever were an amount, putting the placeholder back restores it.

Detection is by the shape of the identifier (a card number must also pass
the Luhn check), never by the words around it.
"""

import re
from collections.abc import Callable

from pydantic import BaseModel

# Each kind, in the order they're looked for: a longer or more specific
# shape first, so an email isn't half-read as a UPI ID, or a card number
# as a phone number.
_PATTERNS: list[tuple[str, re.Pattern[str], Callable[[str], bool] | None]] = []


def _luhn(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _kind(name: str, pattern: str, check: Callable[[str], bool] | None = None, flags: int = 0) -> None:
    _PATTERNS.append((name, re.compile(pattern, flags), check))


_kind("EMAIL", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", flags=re.IGNORECASE)
# name@bank, with no dot after the bank (that would be an email).
_kind("UPI", r"(?<![\w.@-])[\w.-]{2,}@[a-z]{2,}\b(?![.@-]?\w)", flags=re.IGNORECASE)
_kind("CARD", r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])", check=_luhn)
_kind("AADHAAR", r"(?<![\d-])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\d-])")
_kind("PAN", r"\b[A-Z]{5}\d{4}[A-Z]\b", flags=re.IGNORECASE)
_kind(
    "PHONE",
    r"(?:"
    # Fixed group sizes, so an amount after the number ("... 43210 500")
    # is never taken as more of it.
    r"(?:\+91[ -]?|(?<![\d-])(?:0|91[ -]?)?)[6-9]\d{4}[ -]?\d{5}"  # +91 98765 43210, 09876543210
    r"|\+(?!91)\d{1,3}[ -]?\d{2,4}[ -]?\d{3,4}[ -]?\d{3,4}"  # +1 415 555 0100, +44 20 7946 0958
    r"|(?<![\d-])0\d{2,4}-\d{6,8}"           # 022-12345678
    r")(?![\d-])",
)
_kind("ACCOUNT", r"(?<![\d-])\d{11,18}(?![\d-])")

_PLACEHOLDER = re.compile(r"\[(" + "|".join(name for name, _, _ in _PATTERNS) + r")_(\d+)\]", re.IGNORECASE)


class PiiMask:
    """
    One read's placeholders: mask() each text sent to the model (the
    message and any answers, numbered across all of them), then restore()
    the model's answer.
    """

    def __init__(self) -> None:
        self.originals: dict[str, str] = {}
        self._counts: dict[str, int] = {}
        self._seen: dict[str, str] = {}

    def _placeholder(self, kind: str, original: str, text: str) -> str:
        if original in self._seen:
            return self._seen[original]
        while True:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            token = f"[{kind}_{self._counts[kind]}]"
            # Never one the user typed themselves.
            if token.casefold() not in text.casefold():
                break
        self.originals[token] = original
        self._seen[original] = token
        return token

    def mask(self, text: str) -> str:
        """
        Explanation:
            The text with every identifier replaced by a placeholder.

        Parameters:
            text: What the user typed (a message or an answer).

        Returns:
            The text to send to the model.
        """
        masked = text
        for kind, pattern, check in _PATTERNS:
            def swap(match: re.Match[str]) -> str:
                found = match.group(0)
                if check is not None and not check(found):
                    return found
                return self._placeholder(kind, found, text)

            masked = pattern.sub(swap, masked)
        return masked

    @property
    def found(self) -> list[str]:
        """The kinds of data masked ("CARD", ...), once each."""
        return sorted({token[1:].rsplit("_", 1)[0] for token in self.originals})

    def restore(self, value):
        """
        Explanation:
            The model's answer with every placeholder put back as what the
            user typed: in every string, however deep in the answer.

        Parameters:
            value: A string, list, dict or pydantic model.

        Returns:
            The same value, restored.
        """
        if not self.originals:
            return value
        if isinstance(value, str):
            return _PLACEHOLDER.sub(
                lambda m: self.originals.get(f"[{m.group(1).upper()}_{m.group(2)}]", m.group(0)), value
            )
        if isinstance(value, list):
            return [self.restore(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.restore(item) for item in value)
        if isinstance(value, dict):
            return {key: self.restore(item) for key, item in value.items()}
        if isinstance(value, BaseModel):
            return value.model_copy(update={name: self.restore(item) for name, item in value})
        return value
