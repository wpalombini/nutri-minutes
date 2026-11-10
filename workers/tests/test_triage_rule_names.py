"""The rule names the database accepts match the rules in code."""

from pipeline.db.models import TRIAGE_RULES
from pipeline.triage.rules import Rule


def test_rule_names_match_the_database_check() -> None:
    assert tuple(str(rule) for rule in Rule) == TRIAGE_RULES
