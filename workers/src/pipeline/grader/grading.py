"""Turn the model's reading of a paper into a grade.

The model reports what the paper says and suggests how each factor moves the grade. This module
does the arithmetic, so every grade follows the published rules whatever the model says:
- the starting level comes from the design (`starting_level`);
- moves up are capped: never more than one level in total, never for animal or lab studies or
  reviews of them, and never above high certainty;
- the funding and conflicts drop is decided here from the recorded facts, one level at most
  (docs/agents.md, "Evidence Grader: funding and conflicts");
- the level is the starting level plus the moves, kept between 1 (very low) and 4 (high).

The stored reasons carry the moves actually applied, so the level can be checked against them:
`level == clamp(starting_level + raises - lowers, 1, 4)`.
"""

import re
from dataclasses import dataclass
from typing import Any

from pipeline.db.models import (
    DESIGN_CATEGORIES,
    FUNDER_TYPES,
    NOT_GRADABLE_REASONS,
    REVIEW_INCLUDES,
    SPONSOR_ROLES,
    YES_NO_UNKNOWN,
)
from pipeline.models import ModelCallError

MIN_LEVEL, MAX_LEVEL = 1, 4
MAX_RAISE = 1
MODEL_FACTORS = ("design", "size", "duration", "population")
"""Factors the model moves. Funding and conflicts is decided by `funding_lowered`."""
FUNDING = "funding_and_conflicts"
REVIEW_START = {"randomised_trials": 4, "observational": 2, "mixed": 2, "animal_or_lab": 1}
DESIGN_START = {
    "randomised_trial": 4,
    "non_randomised_trial": 2,
    "observational": 2,
    "animal": 1,
    "lab": 1,
}
TRIALS = ("randomised_trial", "non_randomised_trial")
MODEL_FUNDING_SOURCES = ("abstract", "grant_metadata", "not_stated")
"""Sources the model can cite while it reads only abstracts and grant data."""


_ADJECTIVES = r"(?:(?:competing|financial|relevant|potential) ){0,2}"
_CONFLICT = rf"{_ADJECTIVES}(?:interests?|conflicts?(?: of interests?)?)"
NO_CONFLICTS = re.compile(
    r"\s*(?:"
    r"none(?: declared| reported| stated)?|nil|no|n/?a|not applicable"
    r"|nothing to (?:declare|disclose)"
    r"|(?:the )?authors? (?:declare|declared|declares|have|has|report|reported) "
    rf"(?:that they have )?no {_CONFLICT}"
    rf"|(?:there (?:are|were|is|was) )?no {_CONFLICT}"
    r"(?: (?:were |was )?(?:declared|reported|to declare))?"
    r")\.?\s*",
    re.IGNORECASE,
)
"""A whole statement that the authors have no conflicts, stored as no conflicts so it can never
count as a funding concern. Only whole statements match, so "Author A is paid by a dairy council;
the others declare no conflicts" keeps its conflict."""


class ReplyError(ModelCallError):
    """The reply matched the schema but doesn't make sense, such as a review with no basis."""


@dataclass(frozen=True)
class Reason:
    factor: str
    direction: str
    levels: int
    text: str


@dataclass(frozen=True)
class Funding:
    funder: str | None
    funder_type: str
    funding_source: str
    funder_sells_product: str
    sponsor_roles: tuple[str, ...]
    conflicts: str | None
    registered: str
    outcome_switched: str
    surrogate_outcome: bool


@dataclass(frozen=True)
class Grade:
    design_category: str
    review_includes: str | None
    review_reported_level: int | None
    starting_level: int
    level: int
    main_outcome: str
    participants: int | None
    duration: str | None
    population: str | None
    funding: Funding
    funding_lowered: bool
    reasons: tuple[Reason, ...]
    reason: str


@dataclass(frozen=True)
class NotGradable:
    not_gradable: str
    reason: str


def starting_level(design: str, includes: str | None, reported: int | None) -> int:
    if design != "review":
        return DESIGN_START[design]
    if reported is not None:
        return reported
    if includes is None:
        raise ReplyError("A review needs what it combines")
    return REVIEW_START[includes]


def can_raise(design: str, includes: str | None, reported: int | None) -> bool:
    """Animal and lab studies, and reviews of them, never move up. A review that reports its own
    certainty has already counted what would raise it."""
    return design not in ("animal", "lab") and includes != "animal_or_lab" and reported is None


def declared_conflicts(text: str | None) -> str | None:
    """The authors' declared conflicts, or None when there are none."""
    if text is None or NO_CONFLICTS.fullmatch(text):
        return None
    return text


def funding_lowered(funding: Funding, design: str, risks_counted_elsewhere: bool) -> bool:
    """Whether funding and conflicts lowers the grade: a funding concern with a concrete risk,
    not already used to lower another factor."""
    sponsor_ran_it = funding.funder_sells_product == "yes" and bool(
        {"analysis", "writing"} & set(funding.sponsor_roles)
    )
    if sponsor_ran_it:
        return True
    concern = (
        funding.funder_type == "industry"
        or funding.funder_sells_product == "yes"
        or bool(funding.conflicts)
    )
    risk = (
        funding.outcome_switched == "yes"
        or (funding.registered == "no" and design in TRIALS)
        or funding.surrogate_outcome
    )
    return concern and risk and not risks_counted_elsewhere


def _text(reply: dict[str, Any], key: str) -> str | None:
    value = reply.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReplyError(f"Reply {key} isn't text")
    return value.strip() or None


def _choice(reply: dict[str, Any], key: str, allowed: tuple[str, ...]) -> str:
    value = reply.get(key)
    if value not in allowed:
        raise ReplyError(f"Reply {key} isn't one of {', '.join(allowed)}")
    return str(value)


def _funding(reply: dict[str, Any]) -> Funding:
    funder_type = _choice(reply, "funder_type", FUNDER_TYPES)
    source = _choice(reply, "funding_source", MODEL_FUNDING_SOURCES)
    funder = _text(reply, "funder")
    if funder_type == "not_stated" and source != "not_stated":
        # The model found no funder type it could name, so treat the funding as not stated
        # rather than fail the article (run 16: "not stated" with source "abstract").
        source, funder = "not_stated", None
    if source == "not_stated" and funder_type != "not_stated":
        # A named funder type with no source could hide an industry funder; fail instead.
        raise ReplyError("Funding source and funder type disagree on whether funding is stated")
    roles = reply.get("sponsor_roles")
    if not isinstance(roles, list) or not set(roles) <= set(SPONSOR_ROLES):
        raise ReplyError("Reply sponsor_roles aren't a list of roles")
    surrogate = reply.get("surrogate_outcome")
    if not isinstance(surrogate, bool):
        raise ReplyError("Reply has no surrogate_outcome true or false")
    return Funding(
        funder=funder,
        funder_type=funder_type,
        funding_source=source,
        funder_sells_product=_choice(reply, "funder_sells_product", YES_NO_UNKNOWN),
        sponsor_roles=tuple(r for r in SPONSOR_ROLES if r in roles),
        conflicts=declared_conflicts(_text(reply, "conflicts")),
        registered=_choice(reply, "registered", YES_NO_UNKNOWN),
        outcome_switched=_choice(reply, "outcome_switched", YES_NO_UNKNOWN),
        surrogate_outcome=surrogate,
    )


def _moves(reply: dict[str, Any]) -> list[Reason]:
    moves = reply.get("moves")
    if not isinstance(moves, list):
        raise ReplyError("Reply moves aren't a list")
    reasons = []
    for move in moves:
        if not isinstance(move, dict):
            raise ReplyError("A move isn't an object")
        levels = move.get("levels")
        text = _text(move, "text")
        if type(levels) is not int or not 0 <= levels <= 2:
            raise ReplyError("A move's levels aren't 0, 1 or 2")
        if text is None:
            raise ReplyError("A move has no text")
        reasons.append(
            Reason(
                _choice(move, "factor", MODEL_FACTORS),
                _choice(move, "direction", ("raises", "lowers")),
                levels,
                text,
            )
        )
    return reasons


def _apply_caps(reasons: list[Reason], start: int, allow_raise: bool) -> list[Reason]:
    """Reduce raises to what the caps allow, dropping any left at 0 levels, because readers see
    every raise under "Raises certainty". Lowers are kept as given; the level is floored at very
    low instead."""
    room = min(MAX_RAISE, MAX_LEVEL - start) if allow_raise else 0
    capped = []
    for reason in reasons:
        if reason.direction == "raises":
            levels = min(reason.levels, room)
            room -= levels
            if levels == 0:
                continue
            reason = Reason(reason.factor, reason.direction, levels, reason.text)
        capped.append(reason)
    return capped


def level_from(start: int, reasons: tuple[Reason, ...]) -> int:
    moved = sum(r.levels if r.direction == "raises" else -r.levels for r in reasons)
    return max(MIN_LEVEL, min(MAX_LEVEL, start + moved))


def parse_reply(reply: dict[str, Any]) -> Grade | NotGradable:
    """Read the model's reply and compute the grade. The client has checked the schema; this
    checks the meaning and applies the rules."""
    reason = _text(reply, "reason")
    if reason is None:
        raise ReplyError("Reply has no reason")
    if reply.get("gradable") is False:
        not_gradable = _choice(reply, "not_gradable", NOT_GRADABLE_REASONS)
        return NotGradable(not_gradable, reason)
    if reply.get("gradable") is not True:
        raise ReplyError("Reply has no gradable true or false")
    if reply.get("not_gradable") != "none":
        raise ReplyError("A gradable reply gives a reason it isn't gradable")

    design = _choice(reply, "design_category", DESIGN_CATEGORIES)
    includes: str | None = None
    reported: int | None = None
    if design == "review":
        includes = _choice(reply, "review_includes", REVIEW_INCLUDES)
        value = reply.get("review_reported_level")
        if value is not None and (type(value) is not int or not 1 <= value <= 4):
            raise ReplyError("Reply review_reported_level isn't 1 to 4")
        reported = value
    main_outcome = _text(reply, "main_outcome")
    if main_outcome is None:
        raise ReplyError("Reply has no main outcome")
    participants = reply.get("participants")
    if participants is not None and (type(participants) is not int or participants < 1):
        raise ReplyError("Reply participants isn't a positive whole number")
    counted_elsewhere = reply.get("funding_risks_counted_elsewhere")
    if not isinstance(counted_elsewhere, bool):
        raise ReplyError("Reply has no funding_risks_counted_elsewhere true or false")

    funding = _funding(reply)
    start = starting_level(design, includes, reported)
    reasons = _apply_caps(_moves(reply), start, can_raise(design, includes, reported))
    lowered = funding_lowered(funding, design, counted_elsewhere)
    concern = _text(reply, "funding_concern")
    if lowered and concern is None:
        raise ReplyError("Funding lowers the grade, but the reply has no funding_concern text")
    if concern is not None:
        reasons.append(Reason(FUNDING, "lowers", 1 if lowered else 0, concern))

    final = tuple(reasons)
    return Grade(
        design_category=design,
        review_includes=includes,
        review_reported_level=reported,
        starting_level=start,
        level=level_from(start, final),
        main_outcome=main_outcome,
        participants=participants,
        duration=_text(reply, "duration"),
        population=_text(reply, "population"),
        funding=funding,
        funding_lowered=lowered,
        reasons=final,
        reason=reason,
    )
