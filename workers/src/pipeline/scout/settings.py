"""Scout settings, from environment variables with documented defaults."""

import os
import tomllib
from dataclasses import dataclass
from importlib.resources import files

from pipeline.env import float_env, int_env
from pipeline.europe_pmc import ClientSettings


def default_search_terms() -> str:
    text = files("pipeline.scout").joinpath("search_terms.toml").read_text(encoding="utf-8")
    query = tomllib.loads(text).get("query")
    if not isinstance(query, str) or not query.strip():
        raise RuntimeError("search_terms.toml has no query")
    return " ".join(query.split())


@dataclass(frozen=True)
class ScoutSettings:
    search_terms: str
    initial_days: int = 30
    """How far back a run starts when no run has completed yet."""
    overlap_days: int = 2
    """How far each window reaches back before the last completed window's end."""
    max_resumes: int = 3
    """How many times a crashed run is resumed before it's marked failed."""

    @classmethod
    def from_env(cls) -> ScoutSettings:
        return cls(
            search_terms=default_search_terms(),
            initial_days=int_env("SCOUT_INITIAL_DAYS", 30, 1),
            overlap_days=int_env("SCOUT_OVERLAP_DAYS", 2, 0),
            max_resumes=int_env("SCOUT_MAX_RESUMES", 3, 0),
        )


def client_settings_from_env() -> ClientSettings:
    contact = os.environ.get("EUROPE_PMC_CONTACT", "").strip()
    if not contact:
        raise RuntimeError("EUROPE_PMC_CONTACT is not set")
    return ClientSettings(
        contact=contact,
        request_delay_seconds=float_env("EUROPE_PMC_REQUEST_DELAY_SECONDS", 1.0, 0.0),
    )
