"""Read the model's extraction and check it against the abstract.

Every fact must be traceable, so the reply is rejected (and the model asked again) unless:
- each quote appears in the abstract, ignoring differences in whitespace;
- each number in a fact appears in that fact's quote, written the same way, so "0.8" doesn't
  match "0.80" and "95.0" doesn't match "95";
- the main effect's estimate and limits appear in its quote, and a positive estimate isn't
  quoted only with a minus sign;
- the interval's level appears in the abstract with a % sign, "per cent" or "percent";
- the main effect fits the shape `extractions` stores: a known measure, an interval that
  contains its estimate, a level from 50 to below 100, ratios above 0 with no unit,
  mean and risk differences with a unit.
The table checks the shape again, but checking it here means a bad reply is asked again instead
of failing the article on a database error.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pipeline.db.models import EFFECT_MEASURES, EXTRACTION_FACT_KINDS, RATIO_MEASURES
from pipeline.models import ModelCallError

NO_MEASURE = "none"
DIFFERENCES_WITH_UNIT = ("mean_difference", "risk_difference")
MIN_CI_LEVEL, MAX_CI_LEVEL = Decimal(50), Decimal(100)
EFFECT_FIELDS = (
    "estimate",
    "ci_lower",
    "ci_upper",
    "ci_level",
    "unit",
    "outcome_label",
    "comparison_label",
    "lower_label",
    "higher_label",
    "effect_quote",
)
"""Reply fields that must all be null when the measure is "none"."""

_WHITESPACE = re.compile(r"\s+")
_SEPARATORS = ",\u00a0\u2009\u202f"
_THOUSANDS = re.compile(rf"(?<![\d.,])\d{{1,3}}(?:[{_SEPARATORS}]\d{{3}})+(?!\d)")
"""A whole number with commas or narrow spaces between digit groups, as in "31,200", whose
separators are removed before comparing. Digits after a decimal point never count."""
_NUMBER = re.compile(r"\d+(?:\.\d+)?|\.\d+")
_DECIMAL = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)")
_LEVEL = re.compile(r"\d+(?:\.\d+)?")
_MINUS_SIGNS = "-\u2212\u2010\u2011\u2013"
"""Hyphen-minus, minus, hyphen, non-breaking hyphen and en dash. Right after a digit they join a
range, as in "0.70-0.91", so they count as a minus sign only when no digit comes before them."""


class ReplyError(ModelCallError):
    """The reply matched the schema but fails a check, such as a quote not in the abstract."""


@dataclass(frozen=True)
class Fact:
    kind: str
    fact: str
    quote: str


@dataclass(frozen=True)
class MainEffect:
    measure: str
    estimate: Decimal
    ci_lower: Decimal | None
    ci_upper: Decimal | None
    ci_level: Decimal | None
    unit: str | None
    outcome_label: str
    comparison_label: str
    lower_label: str
    higher_label: str
    quote: str


@dataclass(frozen=True)
class Extraction:
    population: str
    population_quote: str
    intervention: str
    intervention_quote: str
    comparator: str | None
    comparator_quote: str | None
    effect: MainEffect | None
    facts: tuple[Fact, ...]


def normalise(text: str) -> str:
    """Text as quotes are compared: Unicode NFC, with each run of whitespace as one space."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def _drop_separators(match: re.Match[str]) -> str:
    return re.sub(f"[{_SEPARATORS}]", "", match.group())


def _number_form(text: str) -> str:
    return normalise(_THOUSANDS.sub(_drop_separators, unicodedata.normalize("NFC", text)))


def numbers_in(text: str) -> list[str]:
    """The numbers in a text as written, with thousands separators removed."""
    return _NUMBER.findall(_number_form(text))


def _occurrences(number: str, text: str) -> list[re.Match[str]]:
    """Where `number` appears in `text` as a whole number, not part of a longer one."""
    pattern = rf"(?<![\d.]){re.escape(number)}(?!\.?\d)"
    return list(re.finditer(pattern, _number_form(text)))


def appears(number: str, text: str) -> bool:
    return bool(_occurrences(number, text))


def _has_minus(match: re.Match[str]) -> bool:
    text, start = match.string, match.start()
    if start == 0 or text[start - 1] not in _MINUS_SIGNS:
        return False
    return start == 1 or not text[start - 2].isdigit()


def _text(reply: dict[str, Any], key: str) -> str | None:
    value = reply.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReplyError(f"Reply {key} isn't text")
    return value.strip() or None


def _required(reply: dict[str, Any], key: str) -> str:
    value = _text(reply, key)
    if value is None:
        raise ReplyError(f"Reply has no {key}")
    return value


def _cuts_a_number(text: str, start: int, end: int) -> bool:
    """Whether text[start:end] begins or ends partway through a number, or just after its minus
    sign, so a quote of "0.97" from "0.975", or "1.2 kg" from "-1.2 kg", is rejected."""
    before = text[start - 1] if start > 0 else ""
    before2 = text[start - 2] if start > 1 else ""
    after = text[end] if end < len(text) else ""
    after2 = text[end + 1] if end + 1 < len(text) else ""
    first, last = text[start], text[end - 1]
    if first in _MINUS_SIGNS and before.isdigit():
        return True  # a range dash, as in "0.70-0.91", isn't a minus sign
    if first.isdigit() or first == ".":
        if before.isdigit() or before == "." or (before in _SEPARATORS and before2.isdigit()):
            return True
        if before and before in _MINUS_SIGNS and not before2.isdigit():
            return True
    if last.isdigit() and (after.isdigit() or (after in "." + _SEPARATORS and after2.isdigit())):
        return True
    return last == "." and end >= 2 and text[end - 2].isdigit() and after.isdigit()


def _check_quote(quote: str, abstract: str, label: str) -> None:
    # Compared with thousands separators removed, so a quote of "200 women" from "31 200 women"
    # (with a narrow space) is seen to start partway through 31200.
    text, wanted = _number_form(abstract), _number_form(quote)
    start = text.find(wanted)
    if start < 0 or not wanted:
        raise ReplyError(f"The {label} quote isn't in the abstract")
    while start >= 0:
        if not _cuts_a_number(text, start, start + len(wanted)):
            return
        start = text.find(wanted, start + 1)
    raise ReplyError(f"The {label} quote starts or ends partway through a number")


def _check_numbers(text: str, quote: str, label: str) -> None:
    for number in numbers_in(text):
        if not appears(number, quote):
            raise ReplyError(f"{number} in the {label} isn't in its quote")


def _quoted(reply: dict[str, Any], key: str, abstract: str) -> tuple[str, str]:
    value = _required(reply, key)
    quote = _required(reply, f"{key}_quote")
    _check_quote(quote, abstract, key)
    _check_numbers(value, quote, key)
    return value, quote


def _decimal(reply: dict[str, Any], key: str, pattern: re.Pattern[str]) -> tuple[str, Decimal]:
    raw = _required(reply, key)
    if raw[0] in _MINUS_SIGNS:
        raw = "-" + raw[1:]  # a typographic minus, as abstracts write it
    if not pattern.fullmatch(raw):
        raise ReplyError(f"Reply {key} isn't a plain decimal number")
    return raw, Decimal(raw)


def _quoted_number(raw: str, quote: str, label: str) -> dict[int, bool]:
    """Where a reported number appears in the effect quote, each place mapped to whether it is a
    negative number written without its minus sign (negated from words). Raises unless it appears
    there, with a sign that doesn't contradict it."""
    negative = raw.startswith("-")
    found = _occurrences(raw.removeprefix("-"), quote)
    if not found:
        raise ReplyError(f"The {label} {raw} isn't in the effect quote as written")
    # A difference stated in words ("1.2 kg less") is negative without a minus sign, so only a
    # positive number quoted with nothing but a minus sign is a contradiction.
    if not negative:
        found = [m for m in found if not _has_minus(m)]
        if not found:
            raise ReplyError(f"The {label} {raw} is quoted with a minus sign")
    return {m.start(): negative and not _has_minus(m) for m in found}


def _distinct_places(
    estimate: dict[int, bool], lower: dict[int, bool], upper: dict[int, bool]
) -> bool:
    """Whether the estimate and limits can come from three different places in the quote, so one
    number is never reported as two of them. The lower limit comes before the upper, except when
    the estimate and both limits are negated from words: "4.17 days shorter (95% CI 1.90-6.44)"
    is -4.17 (-6.44 to -1.90), so negating swaps the limits' order."""
    return any(
        e not in (lo, up) and (lo < up or (lo > up and estimate[e] and lower[lo] and upper[up]))
        for e in estimate
        for lo in lower
        for up in upper
    )


def _main_effect(reply: dict[str, Any], abstract: str) -> MainEffect | None:
    measure = reply.get("measure")
    if measure == NO_MEASURE:
        filled = [key for key in EFFECT_FIELDS if reply.get(key) is not None]
        if filled:
            raise ReplyError(f"No measure, but the reply gives {', '.join(filled)}")
        return None
    if measure not in EFFECT_MEASURES:
        raise ReplyError(f"Reply measure isn't one of {', '.join(EFFECT_MEASURES)} or none")

    quote = _required(reply, "effect_quote")
    _check_quote(quote, abstract, "effect")
    raw_estimate, estimate = _decimal(reply, "estimate", _DECIMAL)
    estimate_at = _quoted_number(raw_estimate, quote, "estimate")

    limits = [reply.get(key) for key in ("ci_lower", "ci_upper", "ci_level")]
    lower = upper = level = None
    if any(value is not None for value in limits):
        if not all(value is not None for value in limits):
            raise ReplyError("An interval needs both limits and its level")
        raw_lower, lower = _decimal(reply, "ci_lower", _DECIMAL)
        raw_upper, upper = _decimal(reply, "ci_upper", _DECIMAL)
        raw_level, level = _decimal(reply, "ci_level", _LEVEL)
        lower_at = _quoted_number(raw_lower, quote, "lower limit")
        upper_at = _quoted_number(raw_upper, quote, "upper limit")
        if not _distinct_places(estimate_at, lower_at, upper_at):
            raise ReplyError("The estimate and limits aren't three separate numbers in the quote")
        level_pattern = rf"(?<![\d.]){re.escape(raw_level)}(?:\s?%|\s+per\s?cent\b)"
        if not re.search(level_pattern, _number_form(abstract), re.IGNORECASE):
            raise ReplyError(f"The interval's level {raw_level}% isn't in the abstract")
        if not MIN_CI_LEVEL <= level < MAX_CI_LEVEL:
            raise ReplyError(f"The interval's level {raw_level} isn't from 50 to below 100")
        if not lower < upper:
            raise ReplyError("The interval's lower limit isn't below its upper limit")
        if not lower <= estimate <= upper:
            raise ReplyError("The estimate isn't within its interval")

    unit = _text(reply, "unit")
    if measure in RATIO_MEASURES:
        if estimate <= 0 or (lower is not None and lower <= 0):
            raise ReplyError("A ratio and its limits must be above 0")
        if unit is not None:
            raise ReplyError("A ratio has no unit")
    elif measure in DIFFERENCES_WITH_UNIT and unit is None:
        raise ReplyError(f"A {measure.replace('_', ' ')} needs a unit")

    labels = {
        key: _required(reply, key)
        for key in ("outcome_label", "comparison_label", "lower_label", "higher_label")
    }
    for key, value in [*labels.items(), ("unit", unit or "")]:
        for number in numbers_in(value):
            if not appears(number, abstract):
                raise ReplyError(f"{number} in the {key.replace('_', ' ')} isn't in the abstract")
    return MainEffect(
        measure=str(measure),
        estimate=estimate,
        ci_lower=lower,
        ci_upper=upper,
        ci_level=level,
        unit=unit,
        quote=quote,
        **labels,
    )


def _facts(reply: dict[str, Any], abstract: str) -> tuple[Fact, ...]:
    items = reply.get("facts")
    if not isinstance(items, list):
        raise ReplyError("Reply facts aren't a list")
    facts = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ReplyError(f"Fact {position} isn't an object")
        kind = item.get("kind")
        if kind not in EXTRACTION_FACT_KINDS:
            raise ReplyError(f"Fact {position} has no known kind")
        fact = _required(item, "fact")
        quote = _required(item, "quote")
        _check_quote(quote, abstract, f"fact {position}")
        _check_numbers(fact, quote, f"fact {position}")
        facts.append(Fact(str(kind), fact, quote))
    return tuple(facts)


def parse_reply(reply: dict[str, Any], abstract: str) -> Extraction:
    """Read the model's reply and check it against the abstract. The client has checked the
    schema; this checks the meaning. Raises `ReplyError` on the first problem."""
    population, population_quote = _quoted(reply, "population", abstract)
    intervention, intervention_quote = _quoted(reply, "intervention", abstract)
    comparator: str | None = None
    comparator_quote: str | None = None
    if reply.get("comparator") is not None or reply.get("comparator_quote") is not None:
        comparator, comparator_quote = _quoted(reply, "comparator", abstract)
    return Extraction(
        population=population,
        population_quote=population_quote,
        intervention=intervention,
        intervention_quote=intervention_quote,
        comparator=comparator,
        comparator_quote=comparator_quote,
        effect=_main_effect(reply, abstract),
        facts=_facts(reply, abstract),
    )
