"""A fake `ModelClient` for agent tests. It never touches the network.

It renders the prompt, so wrong inputs fail as they would for real, and validates each scripted
reply against the prompt's schema, so a test can't pass with a reply the real client would
reject.
"""

from collections.abc import Callable
from typing import Any

from pipeline.models.client import CallRequest, CallResult, ModelCallError
from pipeline.models.schema import validate

Responder = Callable[[CallRequest], dict[str, Any] | Exception]


class FakeModelClient:
    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.requests: list[CallRequest] = []

    def call(self, request: CallRequest) -> CallResult:
        request.prompt.render(request.inputs)
        self.requests.append(request)
        reply = self._responder(request)
        if isinstance(reply, Exception):
            raise reply
        problems = validate(reply, request.prompt.reply_schema)
        if problems:
            raise ModelCallError("Scripted reply didn't match the schema: " + "; ".join(problems))
        return CallResult(
            reply=reply,
            call_id=len(self.requests),
            model=request.prompt.model,
            prompt_version=request.prompt.version,
            generation_id=None,
            cost_usd=None,
        )
