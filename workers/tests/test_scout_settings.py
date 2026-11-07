"""Scout settings and command-line arguments."""

from datetime import date

import pytest

from pipeline.scout.__main__ import _parse_args
from pipeline.scout.run import Window
from pipeline.scout.settings import ScoutSettings, client_settings_from_env, default_search_terms

TODAY = date(2026, 11, 7)


def test_search_terms_load_as_one_line() -> None:
    terms = default_search_terms()
    assert "nutrition" in terms
    assert "\n" not in terms


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SCOUT_INITIAL_DAYS", "SCOUT_OVERLAP_DAYS", "SCOUT_MAX_RESUMES"):
        monkeypatch.delenv(name, raising=False)
    settings = ScoutSettings.from_env()
    assert (settings.initial_days, settings.overlap_days, settings.max_resumes) == (30, 2, 3)


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_invalid_initial_days(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SCOUT_INITIAL_DAYS", value)
    with pytest.raises(RuntimeError, match="SCOUT_INITIAL_DAYS"):
        ScoutSettings.from_env()


def test_contact_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EUROPE_PMC_CONTACT", "  ")
    with pytest.raises(RuntimeError, match="EUROPE_PMC_CONTACT"):
        client_settings_from_env()


def test_manual_window_arguments() -> None:
    assert _parse_args([], TODAY) is None
    assert _parse_args(
        ["--window-start", "2026-09-01", "--window-end", "2026-09-03"], TODAY
    ) == Window(date(2026, 9, 1), date(2026, 9, 3))


@pytest.mark.parametrize(
    "argv",
    [
        ["--window-start", "2026-09-01"],
        ["--window-start", "2026-09-03", "--window-end", "2026-09-01"],
        ["--window-start", "2026-11-01", "--window-end", "2026-11-08"],
        ["--window-start", "yesterday", "--window-end", "2026-11-01"],
    ],
)
def test_invalid_window_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        _parse_args(argv, TODAY)
