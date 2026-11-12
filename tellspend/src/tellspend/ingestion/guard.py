"""
Finds the parts of a message that talk to the app instead of describing
money: notes to "the system", commands to cancel, delete, void, hide,
ignore or change what is recorded, fake system tags. They are found here,
deterministically, before the model reads the message, and cut out of what
the model is shown, so the model can't be talked into obeying them.

This is one layer of three:
    1. here: what's found is never shown to the model;
    2. the prompt: the model lists anything else that instructs it in
       `instructions` and extracts nothing from it;
    3. the builder (Facts): anything only an instruction backs is dropped,
       whatever the model did with it, and every instruction is listed
       back to the user as ignored.

The patterns look for how a message addresses or commands the app, not
for money words: "cancelled the trip, lost the 2,000 deposit" is a fact
and is left alone; "note for the system: this was cancelled" is not.
"""

import re
import unicodedata

_JOINERS = {"‌", "‍"}


def clean_input(text: str) -> str:
    """
    Explanation:
        What the user typed, without the invisible characters attacks
        hide words with ("del\\u200bete"): format characters (zero-width
        spaces, byte-order marks, direction overrides) are removed, and
        compatibility forms are read as plain ones (NFKC: full-width
        "ＳＹＳＴＥＭ" is SYSTEM). Zero-width joiners stay where scripts
        use them, between two non-ASCII letters (Devanagari, emoji).
        Applied once where text enters the app, so the model, the guard
        and the evidence checks all read the same text.

    Parameters:
        text: What the user typed.

    Returns:
        The same text, cleaned.
    """
    text = unicodedata.normalize("NFKC", text)
    kept = []
    for index, char in enumerate(text):
        if unicodedata.category(char) != "Cf":
            kept.append(char)
            continue
        if char in _JOINERS:
            before = text[index - 1] if index else ""
            after = text[index + 1] if index + 1 < len(text) else ""
            if before and after and not before.isascii() and not after.isascii():
                kept.append(char)
    return "".join(kept)

# Who a message can address when it talks to the app.
_ADDRESSEE = r"(?:system|assistant|a\.?i\.?|admin|administrator|tellspend|chat\s*bot|bot|llm)"
_ADDRESSEE_ANY = r"(?:system|assistant|a\.?i\.?|admin|administrator|developer|tellspend|chat\s*bot|bot|llm|model)"

# Words that may come before a command at the start of a clause.
_LEAD = r"(?:(?:please|pls|kindly|just|also|and|then|now|so|ok|okay)\s+)*"

# Matched anywhere in a sentence.
_ANYWHERE = [
    # A note, instruction or message for/to/from the app.
    rf"\b(?:notes?|instructions?|messages?|commands?|orders?|requests?|reminders?|directives?)\s+"
    rf"(?:for|to|from)\s+(?:the\s+|my\s+|this\s+|your\s+)?{_ADDRESSEE_ANY}\b",
    # The app is said to want something.
    rf"\b(?:the\s+)?{_ADDRESSEE}\s+(?:says|said|wants|requests|requires|instructs|orders|demands|"
    rf"must|should|needs\s+to|has\s+to|is\s+(?:told|instructed|required|ordered))\b",
    # Modes, prompts and overrides.
    r"\b(?:system|admin|administrator|developer|debug|god|root|maintenance|jailbreak|sudo)\s+"
    r"(?:prompts?|mode|override|access|instructions?|commands?|message)\b",
    r"\byou\s+are\s+(?:now|no\s+longer)\b",
    r"\bnew\s+(?:instructions?|rules?|task|orders?)\b",
    r"\byour\s+(?:instructions|rules|guidelines|prompt|programming|training|system\s+prompt)\b",
    # Ignore / forget what came before.
    r"\b(?:ignore|disregard|override|bypass)\s+(?:all|any|the|your|my|previous|prior|above|earlier|"
    r"this|these|that|those|every|everything|what)\b",
    r"\bforget\s+(?:all|everything|your|any|previous|prior|the\s+above|what\s+i)\b",
    # Don't record it / it isn't to be recorded.
    r"\b(?:do\s+not|don'?t|never)\s+(?:record|save|log|store|add|track|count|include|enter|keep|"
    r"show|list|process)\b",
    r"\b(?:should\s*n'?o?t|must\s*n'?o?t|is\s+not\s+to|are\s+not\s+to|not\s+to)\s+be\s+"
    r"(?:recorded|saved|logged|stored|added|tracked|counted|included|shown|kept)\b",
    # Delete / void / hide this entry.
    r"\b(?:delete|void|erase|remove|discard|hide|purge|nullify|scrap|wipe|cancel|undo)\s+"
    r"(?:this|that|it|the)\s+(?:expense|entry|entries|record|transaction|item|line|one|bill|"
    r"payment|repayment|data)\b",
    r"\b(?:delete|void|erase|discard|purge|nullify|wipe)\s+(?:this|that|it)\b",
    # Rewrite what's recorded.
    r"\b(?:record|mark|save|log|set|change|make|treat|enter|update|edit|modify|rewrite|replace|"
    r"register|put)\s+(?:this|it|that|the\s+(?:amount|total|price|currency|payer|split|shares?|date|"
    r"expense|entry))\s+(?:\w+\s+){0,4}?(?:as|to|into)\b",
    r"\bchange\s+[\w']+\s+(?:share|amount|total|payment|split|part)\b",
    r"\b(?:record|save|log|add|enter|put)\s+[^.]{0,30}?\binstead\b",
    r"\bmake\s+it\s+(?:₹|rs\.?|inr|\$|€|£)?\s*\d",
]

# Matched only where a clause starts (they would be facts mid-clause).
_CLAUSE_START = [
    # Talking to the app: "Assistant, ...", "SYSTEM: ...", "admin - ...".
    rf"(?:hey|hi|dear|attention|psst)?[\s,]*(?:the\s+)?{_ADDRESSEE}\s*(?:[:,>]|-\s)",
    # A bare command to destroy or hide it.
    rf"{_LEAD}(?:delete|void|erase|remove|cancel|discard|drop|hide|undo|scrap|wipe|purge|nullify)\b",
]

# Fake markup: tags like the ones the app wraps the message in, or chat
# markers. An opening tag or marker takes everything up to its closing one
# (a marker with none: to the end of its sentence); closing the app's own
# input tag takes everything after it, or, when a fake block opens right
# after it ("</expense_input><system>...</system>"), that block.
_TAG_NAMES = r"(?:system|assistant|user|instructions?|expense_input|clarifications?|user_name|admin|developer|inst)"
_OPEN_TAG = re.compile(rf"<\s*({_TAG_NAMES})\b[^>]*>", re.IGNORECASE)
_BREAKOUT = re.compile(r"<\s*/\s*(?:expense_input|clarifications?|user_name)\s*>", re.IGNORECASE)
_MARKERS = re.compile(r"\[\s*/?\s*(?:system|inst|admin|assistant)\s*\]|<\|[^|>]{1,30}\|>", re.IGNORECASE)
_SPECIAL_TOKEN = re.compile(r"<\|[^|>]{1,30}\|>")
_ANY_TAG = re.compile(r"<\s*([^/<>\s][^<>]{0,40})>")
# Where fake markup ends: what follows is the user's again.
# Any closing tag or [/...] marker, whatever its name (attacks disguise
# names: "</s y s t e m>"); special tokens close in pairs (see
# _closing_tokens).
_CLOSERS = re.compile(r"<\s*/[^<>]{1,40}>|\[\s*/[^\[\]]{1,30}\]")


def _closing_tokens(text: str) -> list[re.Match[str]]:
    """The second of each pair of special tokens (<|start|> ... <|end|>)."""
    return list(_SPECIAL_TOKEN.finditer(text))[1::2]

_ANYWHERE_RE = [re.compile(p, re.IGNORECASE) for p in _ANYWHERE]
_CLAUSE_START_RE = [re.compile(p, re.IGNORECASE) for p in _CLAUSE_START]

# For answers to the app's own questions, only what addresses the app or
# its programming: an answer is where the user corrects the description
# ("make it 500", "remove the dessert", "ignore what I said, it was 300"),
# so commands about the entry are facts there.
_ANSWER_ANYWHERE = [
    _ANYWHERE[0],  # a note / instruction for the system
    _ANYWHERE[1],  # the system says / wants
    _ANYWHERE[2],  # system prompt, admin mode, override...
    _ANYWHERE[3],  # you are now
    _ANYWHERE[4],  # new instructions
    _ANYWHERE[5],  # your instructions / rules / prompt
    r"\b(?:ignore|disregard|override|bypass|forget)\s+(?:\w+\s+){0,3}?"
    r"(?:instructions?|rules?|prompts?|guidelines|programming|system)\b",
]
_ANSWER_ANYWHERE_RE = [re.compile(p, re.IGNORECASE) for p in _ANSWER_ANYWHERE]
_ANSWER_CLAUSE_START_RE = [_CLAUSE_START_RE[0]]  # "SYSTEM: ...", "Assistant, ..."

# A sentence ends at . ! ? । } followed by space (not inside 6.50), or a
# newline; and right where fake markup closes (see _sentences).
_SENTENCE_END = re.compile(r"(?<=[.!?।}])\s+|\n+")
# A clause starts after ", " "; " ": " " - " " — " (not inside 1,200).
_CLAUSE_BREAK = re.compile(r"[,;:]\s+|\s[-–—]\s|\s*[—–]\s*")


def _sentences(text: str) -> list[tuple[int, int]]:
    cuts = sorted(
        [(m.start(), m.end()) for m in _SENTENCE_END.finditer(text)]
        + [(m.end(), m.end()) for m in [*_CLOSERS.finditer(text), *_closing_tokens(text)]]
    )
    spans, start = [], 0
    for cut_start, cut_end in cuts:
        if cut_start < start:
            continue
        spans.append((start, cut_start))
        start = cut_end
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def _instruction_start(text: str, start: int, end: int, answer: bool = False) -> int | None:
    """Where the instruction in this sentence starts (its clause), or None."""
    anywhere = _ANSWER_ANYWHERE_RE if answer else _ANYWHERE_RE
    clause_start = _ANSWER_CLAUSE_START_RE if answer else _CLAUSE_START_RE
    sentence = text[start:end]
    clauses = sorted(
        [0]
        + [m.end() for m in _CLAUSE_BREAK.finditer(sentence)]
        # Fake markup starts a new clause: what's before it is the user's.
        + [m.start() for pattern in (_MARKERS, _OPEN_TAG, _BREAKOUT) for m in pattern.finditer(sentence)]
    )
    found: list[int] = []

    for pattern in anywhere:
        if match := pattern.search(sentence):
            found.append(match.start())

    for clause in clauses:
        rest = sentence[clause:]
        lead = len(rest) - len(rest.lstrip(" \t\"'“‘(*-"))
        for pattern in clause_start:
            if pattern.match(rest, lead):
                found.append(clause + lead)

    if not found:
        return None
    first = min(found)
    # From the start of the clause the instruction begins in.
    return start + max(c for c in clauses if c <= first)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def instruction_spans(text: str, answer: bool = False) -> list[tuple[int, int]]:
    """
    Explanation:
        Where the message talks to the app instead of saying what
        happened: each span runs from the start of the clause the
        instruction begins in to the end of its sentence (fake markup: to
        its closing tag, or to the end after closing the app's own tag).

    Parameters:
        text: What the user typed.
        answer: True for an answer to one of the app's questions: only
            what addresses the app is an instruction there (corrections
            to the entry are what answers are for). Fake markup counts
            either way.

    Returns:
        (start, end) offsets into text, sorted and not overlapping.
    """
    # Curly quotes as straight ones, one character for one, so offsets hold.
    plain = text.replace("’", "'").replace("‘", "'")
    spans: list[tuple[int, int]] = []

    for match in _BREAKOUT.finditer(plain):
        # Any tag right after it, whatever its name, ends at its own close.
        after = match.end() + len(plain[match.end():]) - len(plain[match.end():].lstrip())
        block, closing = _ANY_TAG.match(plain, after), None
        if block:
            close = re.compile(rf"<\s*/\s*{re.escape(block.group(1).strip())}\s*>", re.IGNORECASE)
            closing = close.search(plain, block.end())
        spans.append((match.start(), closing.end() if closing else len(plain)))
    for match in _OPEN_TAG.finditer(plain):
        close = re.compile(rf"<\s*/\s*{re.escape(match.group(1))}\s*>", re.IGNORECASE)
        closing = close.search(plain, match.end())
        spans.append((match.start(), closing.end() if closing else len(plain)))
    for match in _MARKERS.finditer(plain):
        sentence_end = next((b for a, b in _sentences(plain) if a <= match.start() < b), len(plain))
        spans.append((match.start(), sentence_end))

    for start, end in _sentences(plain):
        at = _instruction_start(plain, start, end, answer)
        if at is not None:
            spans.append((at, end))

    # Trim whitespace so each span is exactly the words typed.
    trimmed = []
    for a, b in _merge(spans):
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if a < b:
            trimmed.append((a, b))
    return trimmed


def split_instructions(text: str, answer: bool = False) -> tuple[str, list[str]]:
    """
    Explanation:
        The message with every instruction cut out, and the
        instructions, verbatim.

    Parameters:
        text: What the user typed.
        answer: True for an answer to one of the app's questions (see
            instruction_spans).

    Returns:
        (what the model may read, the instructions found).
    """
    spans = instruction_spans(text, answer)
    if not spans:
        return text, []

    # Cut cleanly: a marker in place of the cut ("…") makes the model read
    # the rest differently (measured: "split 60/40 … " lost its split).
    # Evidence can't run across a cut anyway: the builder checks it
    # against its own copy of the text with the instructions cut out.
    kept, cursor = [], 0
    for a, b in spans:
        kept.append(text[cursor:a])
        cursor = b
    kept.append(text[cursor:])
    cleaned = " ".join(" ".join(kept).split()).strip(" ,;:—–-")
    return cleaned, [text[a:b] for a, b in spans]
