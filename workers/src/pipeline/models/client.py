"""The model client interface and the rules every implementation shares (ADR 0005).

Agents call `ModelClient.call` with a loaded prompt and its inputs. The client renders the
prompt, checks the stage's budget for the run, sends the request with retries, validates the
reply and records every attempt through a `CallLog`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from pipeline.env import decimal_env
from pipeline.models.prompts import Prompt

MILLION = Decimal(1_000_000)
MESSAGE_OVERHEAD_TOKENS = 64
"""Added to the prompt side of the worst case for chat formatting tokens the provider adds."""


class ModelCallError(Exception):
    """This call failed. The item it was for fails, and the run carries on."""


class StopRun(Exception):
    """The run can't make more calls and must stop as failed."""


class BudgetExceeded(StopRun):
    """The call could take the stage's spend for this run over its budget."""


class OutOfCredits(StopRun):
    """The provider refused the call for lack of credits (HTTP 402)."""


class NotAuthorised(StopRun):
    """The provider rejected the API key (HTTP 401)."""


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    INVALID_REPLY = "invalid_reply"
    """A reply arrived but wasn't JSON matching the prompt's schema."""
    ERROR = "error"
    """The request failed: an HTTP error, a timeout or an error in the response body."""
    REFUSED = "refused"
    """The budget check refused the attempt, so nothing was sent."""


@dataclass(frozen=True)
class CallRequest:
    run_id: int
    prompt: Prompt
    inputs: Mapping[str, str]
    article_id: int | None = None


@dataclass(frozen=True)
class CallResult:
    reply: dict[str, Any]
    call_id: int
    """The `model_calls` row of the attempt that succeeded, for outputs to reference."""
    model: str
    prompt_version: str
    generation_id: str | None
    cost_usd: Decimal | None


@dataclass(frozen=True)
class CallAttempt:
    """One attempt, as stored in `model_calls`."""

    run_id: int
    stage: str
    article_id: int | None
    prompt_name: str
    prompt_version: str
    attempt: int
    input_values: Mapping[str, str]
    model_requested: str
    max_cost_usd: Decimal
    outcome: Outcome
    model_answered: str | None = None
    provider: str | None = None
    generation_id: str | None = None
    http_status: int | None = None
    raw_reply: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    error: str | None = None


class CallLog(Protocol):
    def record(self, attempt: CallAttempt) -> int:
        """Store the attempt and return its ID. It must persist even if the caller rolls back."""
        ...

    def spent_usd(self, run_id: int, stage: str) -> Decimal:
        """The stage's spend in this run: each sent attempt's reported cost, or its worst case
        when no cost was reported."""
        ...


class ModelClient(Protocol):
    def call(self, request: CallRequest) -> CallResult:
        """Raises `ModelCallError` when this call failed, or `StopRun` when the run must stop.
        Raises `PromptError` when the inputs don't match the prompt, which is a code bug."""
        ...


def worst_case_cost(prompt: Prompt, request_bytes: int) -> Decimal:
    """An upper bound on one attempt's cost in US dollars.

    The request body's UTF-8 length stands in for its token count, which it can't be below for
    the byte-level tokenisers models use. The reply is priced at its full `max_tokens`, plus
    any reasoning limit that doesn't count within it.
    """
    caps = prompt.price_caps
    reply_tokens = prompt.max_tokens
    if prompt.reasoning is not None and prompt.reasoning.counted_separately:
        reply_tokens += prompt.reasoning.max_tokens or 0
    prompt_tokens = request_bytes + MESSAGE_OVERHEAD_TOKENS
    return (
        Decimal(prompt_tokens) * caps.prompt_per_million / MILLION
        + Decimal(reply_tokens) * caps.completion_per_million / MILLION
        + caps.per_request
    )


def budget_env_name(stage: str) -> str:
    return f"MODEL_BUDGET_USD_{stage.upper()}"


def stage_budget(stage: str, default: Decimal) -> Decimal:
    """A stage's budget per run in US dollars, from `MODEL_BUDGET_USD_<STAGE>` or the default."""
    return decimal_env(budget_env_name(stage), default, Decimal(0))


def check_budget(
    log: CallLog, budgets: Mapping[str, Decimal], run_id: int, stage: str, max_cost: Decimal
) -> Decimal:
    """Raise `BudgetExceeded` if the attempt could overspend. Returns the spend so far."""
    if stage not in budgets:
        raise BudgetExceeded(f"No budget is set for stage {stage!r}")
    spent = log.spent_usd(run_id, stage)
    if spent + max_cost > budgets[stage]:
        raise BudgetExceeded(
            f"Stage {stage!r} has spent ${spent:.6f} of ${budgets[stage]:.6f} in run {run_id}, "
            f"and the next call could cost up to ${max_cost:.6f}"
        )
    return spent
