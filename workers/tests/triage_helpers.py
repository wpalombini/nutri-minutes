"""Shared setup for Triage tests: articles, a Triage-shaped prompt and a logged fake client."""

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, text

from pipeline.db.models import TOPIC_SLUGS
from pipeline.models.calls import PostgresCallLog
from pipeline.models.client import CallAttempt, CallRequest, CallResult, Outcome
from pipeline.models.fake import FakeModelClient
from pipeline.models.prompts import Prompt
from tests.prompt_files import settings, write_prompt

TEMPLATE = """--- system ---
You decide whether papers are in scope.

--- user ---
Title: {{ title }}
Types: {{ publication_types }}
Abstract: {{ abstract }}
"""

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "in_scope": {"type": "boolean"},
        "relevance": {"type": "integer", "minimum": 1, "maximum": 5},
        "topics": {
            "type": "array",
            "items": {"type": "string", "enum": list(TOPIC_SLUGS)},
            "maxItems": len(TOPIC_SLUGS),
        },
        "primary_topic": {"type": "string", "enum": [*TOPIC_SLUGS, "none"]},
        "reason": {"type": "string", "maxLength": 400},
    },
    "required": ["in_scope", "relevance", "topics", "primary_topic", "reason"],
    "additionalProperties": False,
}


def triage_prompt(root: Path) -> Prompt:
    return write_prompt(
        root, "triage/scope", TEMPLATE, settings(reply_schema=REPLY_SCHEMA, max_tokens=300)
    )


def in_scope(topic: str = "bone-health", *others: str) -> dict[str, Any]:
    return {
        "in_scope": True,
        "relevance": 4,
        "topics": [topic, *others],
        "primary_topic": topic,
        "reason": "Diet and bone outcomes in older adults.",
    }


def out_of_scope() -> dict[str, Any]:
    return {
        "in_scope": False,
        "relevance": 1,
        "topics": [],
        "primary_topic": "none",
        "reason": "Sports performance, not a health outcome.",
    }


def insert_article(conn: Connection, number: int, **overrides: Any) -> int:
    values: dict[str, Any] = {
        "pmid": str(number),
        "title": f"Study {number}",
        "abstract": "Synthetic abstract.",
        "language": "eng",
        "publication_types": ["Journal Article", "Randomized Controlled Trial"],
    }
    values.update(overrides)
    return int(
        conn.execute(
            text(
                "INSERT INTO articles (pmid, title, abstract, language, publication_types, "
                "source, source_record) VALUES (:pmid, :title, :abstract, :language, "
                ":publication_types, 'europe_pmc', CAST('{}' AS jsonb)) RETURNING id"
            ),
            values,
        ).scalar_one()
    )


class LoggedFakeClient(FakeModelClient):
    """A fake client that also stores a `model_calls` row, so decisions can reference it."""

    def __init__(
        self, engine: Engine, responder: Callable[[CallRequest], dict[str, Any] | Exception]
    ) -> None:
        super().__init__(responder)
        self._log = PostgresCallLog(engine)

    def call(self, request: CallRequest) -> CallResult:
        result = super().call(request)
        call_id = self._log.record(
            CallAttempt(
                run_id=request.run_id,
                stage=request.prompt.stage,
                article_id=request.article_id,
                prompt_name=request.prompt.name,
                prompt_version=request.prompt.version,
                attempt=1,
                input_values=request.inputs,
                model_requested=request.prompt.model,
                max_cost_usd=Decimal("0.001"),
                outcome=Outcome.SUCCEEDED,
                raw_reply="{}",
            )
        )
        return CallResult(
            reply=result.reply,
            call_id=call_id,
            model=result.model,
            prompt_version=result.prompt_version,
            generation_id=None,
            cost_usd=None,
        )
