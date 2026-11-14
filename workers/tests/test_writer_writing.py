"""The Writer's checks on a reply: shape, numbers, wording, copying, reading level and funding."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

import pytest

from pipeline.writer.run import Effect, WriterArticle, prompt_inputs, source_for
from pipeline.writer.writing import (
    ReplyError,
    limit_range,
    parse_reply,
    reading_grade,
    syllables,
)
from tests.extractor_helpers import ABSTRACT
from tests.writer_helpers import PARAGRAPHS, written

EFFECT = Effect(
    measure="hazard_ratio",
    estimate=Decimal("0.80"),
    ci_lower=Decimal("0.65"),
    ci_upper=Decimal("0.97"),
    ci_level=Decimal("95"),
    unit=None,
    outcome_label="Hip fracture risk",
    comparison_label="Vitamin D compared with placebo",
    lower_label="Lower risk",
    higher_label="Higher risk",
    quote="hazard ratio 0.80, 95% CI 0.65 to 0.97",
)
ARTICLE = WriterArticle(
    id=1,
    title="Vitamin D and hip fractures",
    abstract=ABSTRACT,
    extraction_id=2,
    source_basis="abstract",
    population="1,200 women aged 65 or older",
    population_quote="We randomised 1,200 women aged 65 years or older",
    intervention="800 IU of vitamin D a day for 3 years",
    intervention_quote="800 IU of vitamin D a day or placebo for 3 years",
    comparator="placebo",
    comparator_quote="800 IU of vitamin D a day or placebo",
    effect=EFFECT,
    facts=(
        ("outcome", "Hip fractures", "Hip fractures were less common with vitamin D"),
        (
            "result",
            "Bone density rose by 1.2% (p = 0.03).",
            "Bone density rose by 1.2% (p = 0.03).",
        ),
        (
            "absolute",
            "Falls: 12 of 600 with vitamin D, 25 of 600 with placebo.",
            "Falls occurred in 12 of 600 women taking vitamin D and 25 of 600 taking placebo.",
        ),
        ("limitation", "Adherence was self-reported.", "Adherence was self-reported."),
    ),
    design_category="randomised_trial",
    design="randomised trial",
    level=4,
    reasons=(),
    funder=None,
    funder_type="not_stated",
    funder_sells_product="unknown",
    conflicts=None,
    may_reuse_abstract=False,
)


def _parse(reply: dict[str, Any], article: WriterArticle = ARTICLE) -> Any:
    return parse_reply(reply, source_for(article))


def _with_paragraph(extra: str) -> list[str]:
    return [*PARAGRAPHS[:2], PARAGRAPHS[2] + " " + extra]


def test_a_good_reply_passes() -> None:
    draft = _parse(written())
    assert draft.body == "\n\n".join(PARAGRAPHS)
    assert draft.reading_grade <= 10
    assert len(draft.limits) == 2 and draft.absolute_sentence is not None


def test_text_is_whitespace_normalised() -> None:
    draft = _parse(written(headline="  Daily vitamin D   cut hip fractures  "))
    assert draft.headline == "Daily vitamin D cut hip fractures"


@pytest.mark.parametrize("key", ["headline", "result_sentence", "absolute_sentence"])
def test_one_line_fields_reject_line_breaks(key: str) -> None:
    with pytest.raises(ReplyError, match="one line"):
        _parse(written(**{key: "Falls occurred in 12\nof 600 women."}))


@pytest.mark.parametrize("value", ["", "   ", "..."])
def test_empty_or_wordless_text_is_rejected(value: str) -> None:
    with pytest.raises(ReplyError, match="no headline"):
        _parse(written(headline=value))
    with pytest.raises(ReplyError, match="no words"):
        _parse(written(limits=[value, "It only included older women."]))


def test_a_limit_must_be_one_line() -> None:
    with pytest.raises(ReplyError, match="Limit 1 must be one line"):
        _parse(written(limits=["Self-reported\nadherence.", "Only older women."]))


@pytest.mark.parametrize("count", [1, 5])
def test_paragraph_count(count: int) -> None:
    paragraphs = [" ".join(PARAGRAPHS)] if count == 1 else [*PARAGRAPHS, "More.", "And more."]
    with pytest.raises(ReplyError, match=f"{count} paragraphs"):
        _parse(written(paragraphs=paragraphs))


def test_body_word_count() -> None:
    with pytest.raises(ReplyError, match="words; it needs 150 to 250"):
        _parse(written(paragraphs=PARAGRAPHS[:2]))
    with pytest.raises(ReplyError, match="words; it needs 150 to 250"):
        _parse(written(paragraphs=[*PARAGRAPHS, PARAGRAPHS[0] + " " + PARAGRAPHS[1]]))


def test_limit_count_depends_on_the_fixed_item() -> None:
    assert limit_range(False) == (2, 4)
    assert limit_range(True) == (1, 3)
    with pytest.raises(ReplyError, match="1 limits; give 2 to 4"):
        _parse(written(limits=["Only older women."]))
    observational = replace(ARTICLE, design_category="observational", design="observational")
    _parse(written(limits=["Only older women."]), observational)
    with pytest.raises(ReplyError, match="4 limits; give 1 to 3"):
        _parse(written(limits=["A.", "B b.", "C c.", "D d."]), observational)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("headline", "Daily vitamin D cut hip fractures by 20%"),
        ("result_sentence", "Hip fracture risk was 0.8 times as high with vitamin D."),
        ("absolute_sentence", "About 2 in 100 women fell with vitamin D."),
    ],
)
def test_numbers_must_come_from_the_extraction(key: str, value: str) -> None:
    with pytest.raises(ReplyError, match="isn't in the extracted facts"):
        _parse(written(**{key: value}))


def test_numbers_from_facts_quotes_and_the_effect_pass() -> None:
    _parse(
        written(
            result_sentence="The hazard ratio was 0.80, with a 95% interval from 0.65 to 0.97.",
            headline="Vitamin D for 3 years cut hip fractures in 1200 women",
        )
    )


def test_a_number_inside_a_paragraph_is_checked() -> None:
    with pytest.raises(ReplyError, match="9 in the paragraph 3"):
        _parse(written(paragraphs=_with_paragraph("That is a 9 point gain.")))


def test_a_negative_difference_may_be_written_without_its_sign() -> None:
    effect = replace(
        EFFECT,
        measure="mean_difference",
        estimate=Decimal("-1.2"),
        ci_lower=Decimal("-2.0"),
        ci_upper=Decimal("-0.4"),
        unit="kg",
        quote="-1.2 kg (95% CI -2.0 to -0.4)",
    )
    article = replace(ARTICLE, effect=effect)
    _parse(written(result_sentence="Women lost 1.2 kg less, from 0.4 to 2.0 kg."), article)
    with pytest.raises(ReplyError, match="2 in the result sentence"):
        _parse(written(result_sentence="Women lost 2 kg less."), article)


def test_an_absolute_sentence_needs_absolute_facts() -> None:
    _, fact, quote = ARTICLE.facts[2]
    article = replace(ARTICLE, facts=(*ARTICLE.facts[:2], ("result", fact, quote)))
    with pytest.raises(ReplyError, match="absolute_sentence must be null"):
        _parse(written(), article)
    _parse(written(absolute_sentence=None), article)


@pytest.mark.parametrize("word", ["AI", "A.I.", "AI-written"])
def test_ai_is_rejected(word: str) -> None:
    with pytest.raises(ReplyError, match="artificial intelligence"):
        _parse(written(headline=f"An {word} summary of vitamin D and hip fractures"))


@pytest.mark.parametrize("word", ["aid", "AIDS", "said", "paid"])
def test_words_containing_ai_pass(word: str) -> None:
    _parse(written(headline=f"Vitamin D and hip fractures, {word}"))


@pytest.mark.parametrize(
    "advice",
    [
        "You should take vitamin D.",
        "Talk to your doctor before starting.",
        "Experts recommend more vitamin D.",
        "Consider taking a supplement.",
    ],
)
def test_advice_is_rejected(advice: str) -> None:
    with pytest.raises(ReplyError, match="gives advice"):
        _parse(written(paragraphs=_with_paragraph(advice)))


def test_runs_copied_from_an_abstract_we_may_not_reuse_are_rejected() -> None:
    copied = "Falls occurred in 12 of 600 women taking vitamin D and 25 of 600 taking placebo."
    with pytest.raises(ReplyError, match=r"copies .* from the abstract"):
        _parse(written(paragraphs=_with_paragraph(copied)))
    _parse(written(paragraphs=_with_paragraph(copied)), replace(ARTICLE, may_reuse_abstract=True))


def test_seven_copied_words_pass() -> None:
    # "Adherence was self-reported" plus four more words of the abstract's last two sentences.
    _parse(written(limits=["Falls occurred in 12 of 600 women.", "Only older women."]))


def test_reading_level_above_grade_10_is_rejected() -> None:
    dense = [
        "Supplementation with cholecalciferol substantially diminished osteoporotic fracture "
        "incidence among institutionalised postmenopausal participants, notwithstanding "
        "considerable heterogeneity regarding adherence, comorbidity, concomitant medication "
        "utilisation and baseline biochemical vitamin D concentrations. " * 3
    ] * 2
    with pytest.raises(ReplyError, match="above grade 10"):
        _parse(written(paragraphs=dense))


def test_reading_grade_and_syllables() -> None:
    assert syllables("vitamin") == 3
    assert syllables("randomised") == 3
    assert syllables("made") == 1
    assert syllables("0.80") == 1
    assert reading_grade("The cat sat on the mat. The dog ran.") < 2
    assert reading_grade("") == 0
    # Decimal points don't end sentences, and a last sentence without a full stop still counts.
    assert reading_grade("Risk fell by 0.80 in all") == reading_grade("Risk fell by 0.80 in all.")


def test_funding_must_be_mentioned_when_the_funder_sells_the_product() -> None:
    article = replace(
        ARTICLE, funder="A supplement maker", funder_type="industry", funder_sells_product="yes"
    )
    with pytest.raises(ReplyError, match="who funded the study"):
        _parse(written(), article)
    _parse(written(paragraphs=_with_paragraph("A vitamin maker funded it.")), article)


def test_prompt_inputs_describe_the_article() -> None:
    inputs = prompt_inputs(ARTICLE)
    assert inputs["grade"] == "high certainty (4 of 4)"
    assert inputs["fixed_limit"] == "none" and inputs["limit_count"] == "2 to 4"
    assert inputs["main_effect"].startswith(
        "Hazard ratio 0.80, 95% confidence interval 0.65 to 0.97"
    )
    assert "- absolute: Falls: 12 of 600" in inputs["facts"]
    assert "Funding: not stated in the abstract." in inputs["funding"]
    assert inputs["grade_reasons"].startswith("None")

    observational = replace(
        ARTICLE,
        design_category="observational",
        effect=None,
        reasons=(
            ("size", "lowers", 1, "Only 60 people."),
            ("funding_and_conflicts", "lowers", 0, "x"),
        ),
        funder="Dairy Co",
        funder_type="industry",
        funder_sells_product="yes",
    )
    inputs = prompt_inputs(observational)
    assert inputs["fixed_limit"].startswith("It can't show cause and effect")
    assert inputs["limit_count"] == "1 to 3"
    assert inputs["main_effect"] == "No effect size was extracted for the main outcome."
    assert inputs["grade_reasons"] == (
        "- size, lowers 1 level: Only 60 people.\n- funding and conflicts, concern: x"
    )
    assert "Funder: Dairy Co (industry)." in inputs["funding"]
    assert "sells the product tested: yes" in inputs["funding"]
