"""The single client for model calls (ADR 0005). Agents import from here."""

from pipeline.models.client import (
    BudgetExceeded,
    CallRequest,
    CallResult,
    ModelCallError,
    ModelClient,
    NotAuthorised,
    OutOfCredits,
    StopRun,
    stage_budget,
)
from pipeline.models.prompts import Prompt, PromptError, load_prompt

__all__ = [
    "BudgetExceeded",
    "CallRequest",
    "CallResult",
    "ModelCallError",
    "ModelClient",
    "NotAuthorised",
    "OutOfCredits",
    "Prompt",
    "PromptError",
    "StopRun",
    "load_prompt",
    "stage_budget",
]
