"""Read the model's summary and check it against the extraction and the abstract.

A summary is only as good as the facts under it, so the reply is rejected (and the model asked
again) unless:
- the headline, result sentence and absolute sentence are single lines, and every text has words;
- the body has 2 to 4 paragraphs and 150 to 250 words, and the limits fill the page's 2 to 4
  "does not show" items with the app's fixed first item (so 1 to 3 when it has one);
- every number written in digits appears in the extraction (its fields, facts or quotes), so
  nothing is computed, rounded or brought in from elsewhere;
- an absolute sentence is given only when the extraction has absolute numbers;
- the body reads no higher than grade 10 (Flesch-Kincaid, computed here). The target is grade 8
  to 10, but plain text often scores below 8, so a lower score never fails a summary;
- it never says "AI" and never gives advice;
- it mentions the funding when the funder sells the product tested;
- when the abstract's licence doesn't allow reuse, no run of 8 or more words is copied from it.
- no limit repeats the app's fixed first item (the same text, or a run of 6 or more of its words).
Numbers written as words, such as "twice" or "nine", aren't checked here. The Fact-Checker and
the Hype Detector check meaning later; these are the checks code can make.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pipeline.extractor.extraction import appears, normalise, numbers_in
from pipeline.models import ModelCallError

MIN_PARAGRAPHS, MAX_PARAGRAPHS = 2, 4
MIN_BODY_WORDS, MAX_BODY_WORDS = 150, 250
SHOWN_LIMITS_MIN, SHOWN_LIMITS_MAX = 2, 4
""""What this study does not show" items a reader sees, the app's fixed first item included."""
MAX_READING_GRADE = Decimal(10)
FIXED_LIMIT_RUN_WORDS = 6
"""A limit sharing this many words in a row with the fixed first item repeats it."""
COPY_RUN_WORDS = 8
"""The shortest run of words, copied from an abstract we may not reuse, that fails a summary."""

_WORD = re.compile(r"[^\W_]+(?:['\u2019.-][^\W_]+)*")
_LETTERS = re.compile(r"[^\W\d_]")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)|[:;](?=\s)")
"""A sentence ends at ., ! or ? before a space or the end, never inside a number such as
"0.80". Colons and semicolons count too, as readability formulas usually treat them."""
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")
_AI = re.compile(r"(?<![\w.])A\.?I\.?(?!\w)")
""""AI" or "A.I." as a word, in capitals, so words such as "aid" and "AIDS" pass."""
_ADVICE = re.compile(
    r"\b("
    r"you (?:should|must|need to|ought to|may want to|might want to|could try)"
    r"|(?:we|experts?|doctors?) (?:recommend|advise|suggest you)"
    r"|(?:talk|speak) to your (?:doctor|gp|pharmacist)"
    r"|(?:ask|consult|see) your (?:doctor|gp|pharmacist)"
    r"|consult (?:a|your) (?:doctor|health professional|healthcare provider)"
    r"|(?:^|(?<=[.!?] ))(?:start|stop|try|consider) (?:taking|eating|drinking|adding|using)"
    r"|is (?:recommended|advised) for (?:you|everyone|older adults|adults)"
    r")\b",
    re.IGNORECASE,
)
"""Phrases that tell the reader what to do. Summaries report what a study found; they never
advise. This catches the common forms; the Hype Detector looks for the rest."""
_FUNDING = re.compile(
    r"\b(fund(?:ed|ing|er|ers|s)?|paid for|sponsor(?:ed|s|ship)?|financed|financial support)\b",
    re.IGNORECASE,
)


class ReplyError(ModelCallError):
    """The reply matched the schema but fails a check, such as a number not in the extraction."""


@dataclass(frozen=True)
class Source:
    """What the summary is checked against."""

    numbers_text: tuple[str, ...]
    """Every extraction text a number may come from: fields, labels, facts and quotes."""
    effect_numbers: tuple[Decimal, ...]
    has_absolute: bool
    fixed_limit: str | None
    """The fixed first "does not show" item the app shows for this design, if any."""
    funder_sells_product: bool
    abstract: str
    may_reuse_abstract: bool


@dataclass(frozen=True)
class Draft:
    headline: str
    paragraphs: tuple[str, ...]
    limits: tuple[str, ...]
    result_sentence: str
    absolute_sentence: str | None
    reading_grade: Decimal

    @property
    def body(self) -> str:
        return "\n\n".join(self.paragraphs)


def limit_range(fixed_limit: bool) -> tuple[int, int]:
    """How many limits the Writer gives, so the page shows 2 to 4 with the fixed item."""
    taken = 1 if fixed_limit else 0
    return SHOWN_LIMITS_MIN - taken, SHOWN_LIMITS_MAX - taken


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def syllables(word: str) -> int:
    """A word's syllables, estimated from its vowel groups. Numbers count as one, as a reader
    takes them in at a glance."""
    lower = word.lower()
    if not _LETTERS.search(lower):
        return 1
    count = 0
    for part in re.split(r"['\u2019.-]", lower):
        part = re.sub(r"[^a-z]", "", part)
        if not part:
            continue
        groups = len(_VOWEL_GROUPS.findall(part))
        if part.endswith("e") and not part.endswith(("le", "ee", "ye")) and groups > 1:
            groups -= 1  # a silent final e, as in "made"
        if part.endswith(("ed", "es")) and len(part) > 3 and part[-3] not in "dt" and groups > 1:
            groups -= 1  # "walked", "makes", but not "needed" or "rises"
        count += max(groups, 1)
    return max(count, 1)


def reading_grade(text: str) -> Decimal:
    """The Flesch-Kincaid grade level: 0.39 * words per sentence + 11.8 * syllables per word -
    15.59, to one decimal place."""
    found = words(text)
    if not found:
        return Decimal(0)
    ends = list(_SENTENCE_END.finditer(text))
    tail = text[ends[-1].end() :] if ends else text
    sentences = len(ends) + (1 if words(tail) else 0)  # a last sentence with no full stop
    total = sum(syllables(w) for w in found)
    grade = (
        Decimal("0.39") * Decimal(len(found)) / Decimal(sentences)
        + Decimal("11.8") * Decimal(total) / Decimal(len(found))
        - Decimal("15.59")
    )
    return grade.quantize(Decimal("0.1"))


def _text(reply: dict[str, Any], key: str) -> str | None:
    value = reply.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReplyError(f"Reply {key} isn't text")
    return normalise(value) or None


def _line(reply: dict[str, Any], key: str) -> str:
    value = reply.get(key)
    if isinstance(value, str) and re.search(r"[\r\n]", value.strip()):
        raise ReplyError(f"The {key.replace('_', ' ')} must be one line")
    text = _text(reply, key)
    if text is None or not words(text):
        raise ReplyError(f"Reply has no {key.replace('_', ' ')}")
    return text


def _texts(reply: dict[str, Any], key: str) -> tuple[str, ...]:
    items = reply.get(key)
    if not isinstance(items, list):
        raise ReplyError(f"Reply {key} aren't a list")
    texts = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, str) or not words(item):
            raise ReplyError(f"Item {position} in {key} has no words")
        if key == "limits" and re.search(r"[\r\n]", item.strip()):
            raise ReplyError(f"Limit {position} must be one line")
        texts.append(normalise(item))
    return tuple(texts)


def _check_shape(paragraphs: tuple[str, ...], limits: tuple[str, ...], source: Source) -> None:
    if not MIN_PARAGRAPHS <= len(paragraphs) <= MAX_PARAGRAPHS:
        raise ReplyError(
            f"The body has {len(paragraphs)} paragraphs; it needs {MIN_PARAGRAPHS} to "
            f"{MAX_PARAGRAPHS}"
        )
    count = sum(len(words(p)) for p in paragraphs)
    if not MIN_BODY_WORDS <= count <= MAX_BODY_WORDS:
        raise ReplyError(
            f"The body has {count} words; it needs {MIN_BODY_WORDS} to {MAX_BODY_WORDS}"
        )
    low, high = limit_range(source.fixed_limit is not None)
    if not low <= len(limits) <= high:
        raise ReplyError(f"There are {len(limits)} limits; give {low} to {high}")


def _allowed(number: str, source: Source) -> bool:
    if any(appears(number, text) for text in source.numbers_text):
        return True
    value = Decimal(number)
    return any(value == abs(n) and number == format(abs(n), "f") for n in source.effect_numbers)


def _check_numbers(fields: Iterable[tuple[str, str]], source: Source) -> None:
    for label, text in fields:
        for number in numbers_in(text):
            if not _allowed(number, source):
                raise ReplyError(
                    f"{number} in the {label} isn't in the extracted facts, written the same way: "
                    "use only numbers from the facts, without computing, converting or rounding"
                )


def _check_wording(fields: Iterable[tuple[str, str]]) -> None:
    for label, text in fields:
        if _AI.search(text):
            raise ReplyError(f'The {label} says "AI"; write "artificial intelligence" in full')
        advice = _ADVICE.search(text)
        if advice:
            raise ReplyError(
                f'The {label} gives advice ("{advice.group()}"); report what the study found '
                "and never tell readers what to do"
            )


def _runs(text: str, size: int = COPY_RUN_WORDS) -> set[tuple[str, ...]]:
    found = [w.lower().replace("\u2019", "'") for w in words(text)]
    return {tuple(found[i : i + size]) for i in range(len(found) - size + 1)}


def _check_fixed_limit(limits: tuple[str, ...], source: Source) -> None:
    if source.fixed_limit is None:
        return
    fixed_runs = _runs(source.fixed_limit, FIXED_LIMIT_RUN_WORDS)
    for position, limit in enumerate(limits, start=1):
        if _runs(limit, FIXED_LIMIT_RUN_WORDS) & fixed_runs:
            raise ReplyError(
                f"Limit {position} repeats the page's fixed first item; give a different limit"
            )


def _check_copying(fields: Iterable[tuple[str, str]], source: Source) -> None:
    if source.may_reuse_abstract:
        return
    abstract_runs = _runs(source.abstract)
    for label, text in fields:
        copied = _runs(text) & abstract_runs
        if copied:
            run = " ".join(sorted(copied)[0])
            raise ReplyError(
                f'The {label} copies "{run}" from the abstract, whose licence doesn\'t allow '
                "reuse; say it in your own words"
            )


def parse_reply(reply: dict[str, Any], source: Source) -> Draft:
    """Read the model's reply and check it. The client has checked the schema; this checks the
    content. Raises `ReplyError` with the first problem, worded for the model to fix it."""
    headline = _line(reply, "headline")
    result_sentence = _line(reply, "result_sentence")
    absolute_sentence = None
    if reply.get("absolute_sentence") is not None:
        absolute_sentence = _line(reply, "absolute_sentence")
    paragraphs = _texts(reply, "paragraphs")
    limits = _texts(reply, "limits")
    _check_shape(paragraphs, limits, source)
    _check_fixed_limit(limits, source)
    if absolute_sentence is not None and not source.has_absolute:
        raise ReplyError("The facts have no absolute numbers, so absolute_sentence must be null")

    fields = [
        ("headline", headline),
        ("result sentence", result_sentence),
        *([("absolute sentence", absolute_sentence)] if absolute_sentence else []),
        *((f"paragraph {i}", p) for i, p in enumerate(paragraphs, start=1)),
        *((f"limit {i}", lim) for i, lim in enumerate(limits, start=1)),
    ]
    _check_numbers(fields, source)
    _check_wording(fields)
    _check_copying(fields, source)

    grade = reading_grade("\n\n".join(paragraphs))
    if grade > MAX_READING_GRADE:
        raise ReplyError(
            f"The body reads at grade {grade}, above grade {MAX_READING_GRADE}: use shorter "
            "sentences and plainer words"
        )
    if source.funder_sells_product and not any(_FUNDING.search(p) for p in paragraphs):
        raise ReplyError(
            "The funder sells the product tested, so the body must say who funded the study"
        )
    return Draft(
        headline=headline,
        paragraphs=paragraphs,
        limits=limits,
        result_sentence=result_sentence,
        absolute_sentence=absolute_sentence,
        reading_grade=grade,
    )
