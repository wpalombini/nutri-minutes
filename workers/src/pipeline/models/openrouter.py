"""The OpenRouter implementation of `ModelClient`, over its Chat Completions endpoint.

Response handling follows OpenRouter's API reference, checked on 2026-11-09:
https://openrouter.ai/docs/api-reference/overview and
https://openrouter.ai/docs/api_reference/errors-and-debugging.md
"""

import json
import logging
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from pipeline.env import float_env, int_env
from pipeline.models.client import (
    BudgetExceeded,
    CallAttempt,
    CallLog,
    CallRequest,
    CallResult,
    ModelCallError,
    NotAuthorised,
    Outcome,
    OutOfCredits,
    StopRun,
    check_budget,
    worst_case_cost,
)
from pipeline.models.prompts import Prompt
from pipeline.models.schema import validate

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
CLIENT_TITLE = "research-pipeline"
RETRYABLE_STATUS = frozenset({408, 429})
MAX_RETRY_AFTER_SECONDS = 120.0
MAX_ERROR_CHARS = 500


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str = field(repr=False)
    timeout_seconds: float = 120.0
    max_attempts: int = 3
    backoff_base_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> OpenRouterSettings:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        return cls(
            api_key=key,
            timeout_seconds=float_env("MODEL_TIMEOUT_SECONDS", 120.0, 1.0),
            max_attempts=int_env("MODEL_MAX_ATTEMPTS", 3, 1),
        )


def request_body(prompt: Prompt, messages: list[dict[str, str]]) -> dict[str, Any]:
    caps = prompt.price_caps
    body: dict[str, Any] = {
        "model": prompt.model,
        "messages": messages,
        "max_tokens": prompt.max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": prompt.name.replace("/", "_"),
                "strict": True,
                "schema": prompt.reply_schema,
            },
        },
        "provider": {
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {
                "prompt": str(caps.prompt_per_million),
                "completion": str(caps.completion_per_million),
                "request": str(caps.per_request),
            },
        },
    }
    if prompt.temperature is not None:
        body["temperature"] = prompt.temperature
    if prompt.reasoning is not None:
        body["reasoning"] = prompt.reasoning.request_field()
    return body


@dataclass
class _Reading:
    """What one HTTP exchange came to."""

    outcome: Outcome
    retryable: bool = False
    stop: type[StopRun] | None = None
    reply: dict[str, Any] | None = None
    retry_after: float | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    """Columns for the attempt row read from the response."""


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS] + "…"


def _int_or_none(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _usage_fields(body: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if isinstance(body.get("id"), str):
        fields["generation_id"] = body["id"]
    if isinstance(body.get("model"), str):
        fields["model_answered"] = body["model"]
    # Not in the documented schema for success responses, but sent in practice.
    if isinstance(body.get("provider"), str):
        fields["provider"] = body["provider"]
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return fields
    fields["prompt_tokens"] = _int_or_none(usage.get("prompt_tokens"))
    fields["completion_tokens"] = _int_or_none(usage.get("completion_tokens"))
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        fields["cached_tokens"] = _int_or_none(prompt_details.get("cached_tokens"))
    completion_details = usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        fields["reasoning_tokens"] = _int_or_none(completion_details.get("reasoning_tokens"))
    cost = usage.get("cost")
    if isinstance(cost, int | float) and not isinstance(cost, bool):
        try:
            value = Decimal(str(cost))
        except InvalidOperation:
            value = None
        if value is not None and value.is_finite() and value >= 0:
            fields["cost_usd"] = value
    return fields


def _error_message(body: Any) -> str | None:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = body["error"].get("message")
        if isinstance(message, str):
            return _truncate(message)
    return None


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def read_response(response: httpx.Response, prompt: Prompt) -> _Reading:
    status = response.status_code
    try:
        body: Any = response.json()
    except ValueError:
        body = None
    fields: dict[str, Any] = {"http_status": status}
    if isinstance(body, dict):
        fields.update(_usage_fields(body))
    message = _error_message(body)

    if status != 200:
        fields["error"] = f"HTTP {status}" + (f": {message}" if message else "")
        if status == 401:
            return _Reading(Outcome.ERROR, stop=NotAuthorised, fields=fields)
        if status == 402:
            return _Reading(Outcome.ERROR, stop=OutOfCredits, fields=fields)
        retryable = status in RETRYABLE_STATUS or status >= 500
        return _Reading(
            Outcome.ERROR, retryable=retryable, retry_after=_retry_after(response), fields=fields
        )

    if not isinstance(body, dict):
        fields["error"] = "The response wasn't a JSON object"
        return _Reading(Outcome.ERROR, retryable=True, fields=fields)
    choices = body.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else None
    if not isinstance(choice, dict):
        fields["error"] = "Error in a 200 response: " + (message or "no choices")
        return _Reading(Outcome.ERROR, retryable=True, fields=fields)
    finish = choice.get("finish_reason")
    choice_error = _error_message(choice)
    message_obj = choice.get("message")
    content = message_obj.get("content") if isinstance(message_obj, dict) else None
    if isinstance(content, str):
        fields["raw_reply"] = content
    if finish == "error" or choice_error or message:
        fields["error"] = "Error in a 200 response: " + (choice_error or message or "unknown")
        return _Reading(Outcome.ERROR, retryable=True, fields=fields)
    if finish == "length":
        # The reply, or reasoning before it, used up max_tokens. A retry would do the same.
        fields["error"] = "The reply reached max_tokens"
        return _Reading(Outcome.INVALID_REPLY, fields=fields)
    if finish == "content_filter":
        fields["error"] = "The provider's content filter stopped the reply"
        return _Reading(Outcome.ERROR, fields=fields)
    if not isinstance(content, str):
        fields["error"] = "The reply had no text"
        return _Reading(Outcome.INVALID_REPLY, retryable=True, fields=fields)
    try:
        reply = json.loads(content)
    except ValueError:
        fields["error"] = "The reply wasn't JSON"
        return _Reading(Outcome.INVALID_REPLY, retryable=True, fields=fields)
    problems = validate(reply, prompt.reply_schema)
    if problems:
        fields["error"] = _truncate("The reply didn't match the schema: " + "; ".join(problems))
        return _Reading(Outcome.INVALID_REPLY, retryable=True, fields=fields)
    return _Reading(Outcome.SUCCEEDED, reply=reply, fields=fields)


class OpenRouterClient:
    def __init__(
        self,
        settings: OpenRouterSettings,
        *,
        log: CallLog,
        budgets: Mapping[str, Decimal],
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] = lambda limit: random.uniform(0, limit),  # noqa: S311
    ) -> None:
        self._settings = settings
        self._log = log
        self._budgets = dict(budgets)
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._http = httpx.Client(
            transport=transport,
            timeout=settings.timeout_seconds,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": CLIENT_TITLE,
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OpenRouterClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def call(self, request: CallRequest) -> CallResult:
        prompt = request.prompt
        stage = prompt.stage
        messages = prompt.render(request.inputs)
        payload = json.dumps(request_body(prompt, messages), ensure_ascii=False).encode("utf-8")
        max_cost = worst_case_cost(prompt, len(payload))
        base = CallAttempt(
            run_id=request.run_id,
            stage=stage,
            article_id=request.article_id,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            attempt=0,
            input_values=dict(request.inputs),
            model_requested=prompt.model,
            max_cost_usd=max_cost,
            outcome=Outcome.ERROR,
        )
        attempts = self._settings.max_attempts
        for number in range(1, attempts + 1):
            try:
                check_budget(self._log, self._budgets, request.run_id, stage, max_cost)
            except BudgetExceeded as exc:
                self._log.record(
                    replace(base, attempt=number, outcome=Outcome.REFUSED, error=str(exc))
                )
                logger.error("Model call refused: run=%d stage=%s: %s", request.run_id, stage, exc)
                raise

            started = self._clock()
            try:
                response = self._http.post(API_URL, content=payload)
            except httpx.TransportError as exc:
                reading = _Reading(
                    Outcome.ERROR, retryable=True, fields={"error": type(exc).__name__}
                )
            else:
                reading = read_response(response, prompt)
            latency_ms = round((self._clock() - started) * 1000)

            row = replace(
                base,
                attempt=number,
                outcome=reading.outcome,
                latency_ms=latency_ms,
                **reading.fields,
            )
            call_id = self._log.record(row)
            logger.info(
                "Model call %d: run=%d stage=%s prompt=%s@%s attempt=%d outcome=%s "
                "cost=%s latency_ms=%d",
                call_id,
                request.run_id,
                stage,
                prompt.name,
                prompt.version,
                number,
                reading.outcome,
                row.cost_usd,
                latency_ms,
            )
            if reading.reply is not None:
                return CallResult(
                    reply=reading.reply,
                    call_id=call_id,
                    model=row.model_answered or prompt.model,
                    prompt_version=prompt.version,
                    generation_id=row.generation_id,
                    cost_usd=row.cost_usd,
                )
            problem = row.error or reading.outcome
            if reading.stop is not None:
                raise reading.stop(f"Model call {call_id} stopped the run: {problem}")
            if not reading.retryable or number == attempts:
                raise ModelCallError(f"Model call {call_id} failed: {problem}")
            backoff = self._settings.backoff_base_seconds * 2 ** (number - 1)
            backoff += self._jitter(backoff / 4)
            if reading.retry_after is not None:
                backoff = max(backoff, reading.retry_after)
            logger.warning(
                "Model call %d failed (%s), retrying in %.0fs (attempt %d of %d)",
                call_id,
                problem,
                backoff,
                number,
                attempts,
            )
            self._sleep(backoff)
        raise AssertionError("unreachable")
