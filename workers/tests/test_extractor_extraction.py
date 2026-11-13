"""The Extractor's reply checks: quotes, numbers and the main effect's shape."""

from decimal import Decimal
from typing import Any

import pytest

from pipeline.extractor.extraction import ReplyError, appears, normalise, numbers_in, parse_reply
from tests.extractor_helpers import ABSTRACT, NO_EFFECT, extracted, fact


def _fails(match: str, abstract: str = ABSTRACT, **overrides: Any) -> None:
    with pytest.raises(ReplyError, match=match):
        parse_reply(extracted(**overrides), abstract)


def test_a_good_reply_parses_with_numbers_as_written() -> None:
    extraction = parse_reply(extracted(), ABSTRACT)
    effect = extraction.effect
    assert effect is not None
    assert (effect.estimate, effect.ci_lower, effect.ci_upper) == (
        Decimal("0.80"),
        Decimal("0.65"),
        Decimal("0.97"),
    )
    assert str(effect.estimate) == "0.80" and str(effect.ci_level) == "95"
    assert [f.kind for f in extraction.facts] == ["outcome", "result", "absolute", "limitation"]
    assert extraction.comparator == "placebo"


def test_no_main_effect() -> None:
    assert parse_reply(extracted(**NO_EFFECT), ABSTRACT).effect is None


def test_no_measure_with_effect_fields_fails() -> None:
    _fails("No measure", **{**NO_EFFECT, "estimate": "0.80"})


def test_no_comparator() -> None:
    extraction = parse_reply(extracted(comparator=None, comparator_quote=None), ABSTRACT)
    assert extraction.comparator is None and extraction.comparator_quote is None


def test_comparator_without_quote_fails() -> None:
    _fails("comparator_quote", comparator_quote=None)


def test_quotes_ignore_whitespace_differences() -> None:
    quote = "for 3 years.  Hip fractures"  # a line break in the abstract
    parse_reply(extracted(facts=[fact("outcome", "Hip fractures", quote)]), ABSTRACT)


@pytest.mark.parametrize(
    "field", ["population_quote", "intervention_quote", "comparator_quote", "effect_quote"]
)
def test_a_quote_not_in_the_abstract_fails(field: str) -> None:
    _fails("isn't in the abstract", **{field: "Something the abstract never says"})


def test_a_fact_quote_not_in_the_abstract_fails() -> None:
    _fails("fact 1 quote", facts=[fact("result", "Fewer falls", "Falls were halved")])


def test_a_number_not_in_its_quote_fails() -> None:
    _fails("1,300|1300", population="1,300 women aged 65 or older")
    _fails("13", facts=[fact("absolute", "13 of 600 fell.", "Falls occurred in 12 of 600")])


def test_thousands_separators_match() -> None:
    assert appears("1200", "We randomised 1,200 women")
    assert numbers_in("1,200 women aged 65") == ["1200", "65"]
    parse_reply(extracted(population="1200 women aged 65 or older"), ABSTRACT)


def test_numbers_must_be_written_as_quoted() -> None:
    assert not appears("0.8", "hazard ratio 0.80")
    assert not appears("95.0", "95% CI")
    assert not appears("5", "0.65")
    _fails("estimate 0.8 isn't", estimate="0.8")
    _fails("level 95.0", ci_level="95.0")


def test_estimate_and_limits_must_be_in_the_effect_quote() -> None:
    _fails("lower limit", ci_lower="0.60")
    _fails("upper limit 1.2", ci_upper="1.2")


@pytest.mark.parametrize("value", ["0.80.1", "1e3", "0,80", "+0.80", "0.80%", ""])
def test_numbers_must_be_plain_decimals(value: str) -> None:
    _fails("estimate", estimate=value)


def test_the_level_must_be_stated() -> None:
    _fails("level 90% isn't in the abstract", ci_level="90")


def test_the_level_may_be_stated_elsewhere_in_the_abstract() -> None:
    abstract = "All intervals are 97.5% CIs. Risk fell (OR 0.70, 0.50-0.90)."
    reply = extracted(
        measure="odds_ratio",
        estimate="0.70",
        ci_lower="0.50",
        ci_upper="0.90",
        ci_level="97.5",
        population="adults",
        population_quote="Risk fell",
        intervention="x",
        intervention_quote="Risk fell",
        comparator=None,
        comparator_quote=None,
        effect_quote="OR 0.70, 0.50-0.90",
        facts=[],
    )
    effect = parse_reply(reply, abstract).effect
    assert effect is not None and str(effect.ci_level) == "97.5"


def test_an_interval_needs_all_three_parts() -> None:
    _fails("both limits and its level", ci_level=None)
    effect = parse_reply(extracted(ci_lower=None, ci_upper=None, ci_level=None), ABSTRACT).effect
    assert effect is not None and effect.ci_lower is None


def _difference(abstract: str, quote: str, **overrides: Any) -> dict[str, Any]:
    reply = extracted(
        measure="mean_difference",
        unit="kg",
        population="adults",
        population_quote=abstract[:10],
        intervention="protein",
        intervention_quote=abstract[:10],
        comparator=None,
        comparator_quote=None,
        outcome_label="Muscle mass",
        comparison_label="Protein compared with usual diet",
        lower_label="Less muscle",
        higher_label="More muscle",
        effect_quote=quote,
        facts=[],
    )
    reply.update(overrides)
    return reply


def test_a_negative_difference_with_a_minus_sign() -> None:
    abstract = "Lean mass changed (MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4)."
    reply = _difference(
        abstract,
        "MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4",
        estimate="-1.2",
        ci_lower="-2.0",
        ci_upper="-0.4",
        ci_level="95",
    )
    effect = parse_reply(reply, abstract).effect
    assert effect is not None and effect.estimate == Decimal("-1.2")


def test_a_negative_difference_stated_in_words() -> None:
    abstract = "Lean mass was 1.2 kg lower with the diet."
    reply = _difference(
        abstract, "1.2 kg lower", estimate="-1.2", ci_lower=None, ci_upper=None, ci_level=None
    )
    parse_reply(reply, abstract)


def test_a_positive_estimate_quoted_only_with_a_minus_sign_fails() -> None:
    abstract = "Lean mass changed (MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4)."
    reply = _difference(
        abstract,
        "MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4",
        estimate="1.2",
        ci_lower="-2.0",
        ci_upper="-0.4",
        ci_level="95",
    )
    with pytest.raises(ReplyError, match="minus sign"):
        parse_reply(reply, abstract)


def test_a_range_dash_is_not_a_minus_sign() -> None:
    abstract = "Lean mass rose (MD 1.2 kg, 95% CI 0.4-2.0)."
    reply = _difference(
        abstract,
        "MD 1.2 kg, 95% CI 0.4-2.0",
        estimate="1.2",
        ci_lower="0.4",
        ci_upper="2.0",
        ci_level="95",
    )
    parse_reply(reply, abstract)


def test_differences_need_a_unit() -> None:
    abstract = "Lean mass rose (MD 1.2 kg, 95% CI 0.4-2.0)."
    reply = _difference(
        abstract,
        "MD 1.2 kg, 95% CI 0.4-2.0",
        estimate="1.2",
        ci_lower="0.4",
        ci_upper="2.0",
        ci_level="95",
        unit=None,
    )
    with pytest.raises(ReplyError, match="needs a unit"):
        parse_reply(reply, abstract)
    reply.update(measure="standardised_mean_difference")
    parse_reply(reply, abstract)


def test_a_ratio_has_no_unit() -> None:
    _fails("no unit", unit="risk")


def test_a_ratio_must_be_above_zero() -> None:
    abstract = "The ratio was 0 (95% CI 0 to 0.5)."
    reply = extracted(
        estimate="0", ci_lower="0", ci_upper="0.5", effect_quote="0 (95% CI 0 to 0.5)"
    )
    with pytest.raises(ReplyError, match="above 0"):
        parse_reply(reply, abstract + " " + ABSTRACT)


def test_the_estimate_must_be_inside_its_interval() -> None:
    abstract = ABSTRACT + " Another HR 0.99, 95% CI 0.65 to 0.97."
    _fails(
        "within its interval",
        abstract,
        estimate="0.99",
        effect_quote="HR 0.99, 95% CI 0.65 to 0.97",
    )


def test_limits_must_be_in_order() -> None:
    abstract = ABSTRACT + " Odd: HR 0.80, 95% CI 0.97 to 0.65."
    _fails(
        "below its upper",
        abstract,
        ci_lower="0.97",
        ci_upper="0.65",
        effect_quote="HR 0.80, 95% CI 0.97 to 0.65",
    )


def test_the_level_must_be_from_50_to_below_100() -> None:
    abstract = ABSTRACT + " (100% CI 0.65 to 0.97, 0.80)"
    _fails("from 50", abstract, ci_level="100", effect_quote="(100% CI 0.65 to 0.97, 0.80)")


def test_numbers_in_labels_must_be_in_the_abstract() -> None:
    _fails("comparison label", comparison_label="1,000 IU compared with placebo")
    parse_reply(extracted(comparison_label="800 IU compared with placebo"), ABSTRACT)


def test_unknown_fact_kind_fails() -> None:
    _fails("no known kind", facts=[fact("opinion", "x", "Adherence was self-reported.")])


def test_normalise() -> None:
    assert normalise(" a\n\tb  c ") == "a b c"


def test_a_quote_cannot_cut_a_number() -> None:
    abstract = "Risk fell (HR 0.80, 95% CI 0.65 to 0.975). Mass was -1.2 kg. Density rose 1.25%."
    reply = extracted(effect_quote="HR 0.80, 95% CI 0.65 to 0.97", ci_upper="0.97")
    with pytest.raises(ReplyError, match="partway through a number"):
        parse_reply(reply, abstract + " " + ABSTRACT)
    with pytest.raises(ReplyError, match="partway"):
        parse_reply(
            extracted(facts=[fact("result", "1.2 kg", "1.2 kg")]), abstract + " " + ABSTRACT
        )
    with pytest.raises(ReplyError, match="partway"):
        parse_reply(
            extracted(facts=[fact("result", "Rose 1.2", "rose 1.2")]), abstract + " " + ABSTRACT
        )
    with pytest.raises(ReplyError, match="partway"):
        parse_reply(extracted(facts=[fact("result", "200 women", "200 women")]), ABSTRACT)


def test_a_quote_may_repeat_and_one_clean_place_is_enough() -> None:
    abstract = "Mass was -1.2 kg in men. Mass was 1.2 kg higher in women."
    parse_reply(extracted(facts=[fact("result", "1.2 kg higher", "1.2 kg")]), abstract + ABSTRACT)


def test_estimate_and_limits_are_separate_numbers() -> None:
    _fails("three separate numbers", estimate="0.97")
    _fails("three separate numbers", ci_lower="0.97", ci_upper="0.97")


def test_the_level_needs_a_percent_sign() -> None:
    abstract = ABSTRACT + " We analysed 90 participants (HR 0.80, 0.65 to 0.97)."
    _fails("level 90%", abstract, ci_level="90", effect_quote="HR 0.80, 0.65 to 0.97")


def test_typographic_minus_and_no_leading_zero_are_accepted() -> None:
    abstract = "Lean mass changed (MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4); p = .03."
    reply = _difference(
        abstract,
        "MD \u22121.2 kg, 95% CI \u22122.0 to \u22120.4",
        estimate="\u22121.2",
        ci_lower="-2.0",
        ci_upper="-0.4",
        ci_level="95",
        facts=[fact("result", "p = .03", "p = .03")],
    )
    effect = parse_reply(reply, abstract).effect
    assert effect is not None and effect.estimate == Decimal("-1.2")


def test_thousands_removal_never_joins_decimals() -> None:
    assert numbers_in("0.03,100 people") == ["0.03", "100"]
    assert numbers_in("31,200 and 1,000,000") == ["31200", "1000000"]
