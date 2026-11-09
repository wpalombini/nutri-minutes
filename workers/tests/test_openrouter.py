"""The OpenRouter client, against a mock transport. Nothing here touches the network."""

import email.utils
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from pipeline.models.calls import MemoryCallLog
from pipeline.models.client import (
    BudgetExceeded,
    CallRequest,
    ModelCallError,
    NotAuthorised,
    Outcome,
    OutOfCredits,
    worst_case_cost,
)
from pipeline.models.openrouter import (
    API_URL,
    OpenRouterClient,
    OpenRouterSettings,
    request_body,
)
from pipeline.models.prompts import Prompt, PromptError
from tests.prompt_files import settings, write_prompt

INPUTS = {"title": "Protein and muscle", "abstract": "Older adults…"}
REPLY = {"in_scope": True, "reason": "Muscle in older adults"}


def completion(
    content: str | None = None,
    *,
    finish: str = "stop",
    cost: Any = 0.00042,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "gen-123",
        "model": "example/model-1.0",
        "provider": "ExampleCloud",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(REPLY) if content is None else content,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "cost": cost,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }
    body.update(extra or {})
    return body


class Harness:
    def __init__(self, tmp_path: Path, responses: list[httpx.Response | Exception]) -> None:
        self.prompt: Prompt = write_prompt(tmp_path)
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []
        self.log = MemoryCallLog()
        self.budget = Decimal("1.00")

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def client(self, **settings: Any) -> OpenRouterClient:
        return OpenRouterClient(
            OpenRouterSettings(api_key="sk-test-secret", backoff_base_seconds=1.0, **settings),
            log=self.log,
            budgets={"triage": self.budget},
            transport=httpx.MockTransport(self.handler),
            sleep=self.sleeps.append,
            jitter=lambda _: 0.0,
        )

    def call(self, **settings: Any) -> Any:
        with self.client(**settings) as client:
            return client.call(
                CallRequest(run_id=7, prompt=self.prompt, inputs=INPUTS, article_id=3)
            )


def ok(body: dict[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
    return httpx.Response(200, json=body if body is not None else completion(**kwargs))


def test_success_returns_reply_and_records_attempt(tmp_path: Path) -> None:
    h = Harness(tmp_path, [ok()])
    result = h.call()
    assert result.reply == REPLY
    assert result.call_id == 1
    assert result.cost_usd == Decimal("0.00042")
    assert result.generation_id == "gen-123"
    [row] = h.log.attempts
    assert row.outcome is Outcome.SUCCEEDED
    assert (row.run_id, row.stage, row.article_id, row.attempt) == (7, "triage", 3, 1)
    assert row.prompt_version == h.prompt.version
    assert row.input_values == INPUTS
    assert row.model_answered == "example/model-1.0"
    assert row.provider == "ExampleCloud"
    assert row.http_status == 200
    assert (row.prompt_tokens, row.completion_tokens, row.reasoning_tokens) == (120, 30, 5)
    assert row.raw_reply == json.dumps(REPLY)
    assert row.error is None
    assert row.cost_usd is not None
    assert row.max_cost_usd > row.cost_usd


def test_request_body_and_headers(tmp_path: Path) -> None:
    h = Harness(tmp_path, [ok()])
    h.call()
    [request] = h.requests
    assert str(request.url) == API_URL
    assert request.headers["Authorization"] == "Bearer sk-test-secret"
    body = json.loads(request.content)
    assert body["model"] == "example/model-1.0"
    assert body["max_tokens"] == 1000
    assert body["temperature"] == 0
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "triage_scope", "strict": True, "schema": h.prompt.reply_schema},
    }
    assert body["provider"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": "1.00", "completion": "4.00", "request": "0"},
    }
    assert "models" not in body
    assert body["messages"][1]["content"].startswith("Title: Protein and muscle")


def test_key_is_not_in_settings_repr() -> None:
    assert "sk-test" not in repr(OpenRouterSettings(api_key="sk-test-secret"))


@pytest.mark.parametrize(
    "first",
    [
        httpx.Response(429, headers={"Retry-After": "30"}, json={"error": {"code": 429}}),
        httpx.Response(503, json={"error": {"code": 503, "message": "No provider"}}),
        httpx.Response(408),
        httpx.Response(200, json={"id": "gen-1", "error": {"code": 502, "message": "upstream"}}),
        httpx.Response(200, text="<html>bad gateway</html>"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_transient_failures_are_retried(tmp_path: Path, first: httpx.Response | Exception) -> None:
    h = Harness(tmp_path, [first, ok()])
    assert h.call().reply == REPLY
    assert [a.outcome for a in h.log.attempts] == [Outcome.ERROR, Outcome.SUCCEEDED]
    assert [a.attempt for a in h.log.attempts] == [1, 2]
    expected_wait = 30.0 if isinstance(first, httpx.Response) and first.status_code == 429 else 1.0
    assert h.sleeps == [expected_wait]


def test_error_inside_a_choice_is_retried(tmp_path: Path) -> None:
    errored = completion("partial", finish="error", extra={})
    errored["choices"][0]["error"] = {"code": 502, "message": "provider dropped"}
    h = Harness(tmp_path, [ok(errored), ok()])
    h.call()
    assert h.log.attempts[0].error == "Error in a 200 response: provider dropped"


@pytest.mark.parametrize(
    "content",
    ["not json", json.dumps({"in_scope": "yes", "reason": "x"}), json.dumps({"in_scope": True})],
)
def test_invalid_replies_are_retried_then_fail(tmp_path: Path, content: str) -> None:
    h = Harness(tmp_path, [ok(content=content)] * 3)
    with pytest.raises(ModelCallError, match="Model call 3 failed"):
        h.call()
    assert [a.outcome for a in h.log.attempts] == [Outcome.INVALID_REPLY] * 3
    assert all(a.raw_reply == content for a in h.log.attempts)
    assert h.sleeps == [1.0, 2.0]


def test_content_filter_is_not_retried(tmp_path: Path) -> None:
    h = Harness(tmp_path, [ok(content="", finish="content_filter")])
    with pytest.raises(ModelCallError, match="content filter"):
        h.call()
    assert len(h.requests) == 1


def test_top_level_error_with_choices_is_retried(tmp_path: Path) -> None:
    errored = completion(extra={"error": {"code": 502, "message": "upstream reset"}})
    h = Harness(tmp_path, [ok(errored), ok()])
    assert h.call().reply == REPLY
    assert h.log.attempts[0].error == "Error in a 200 response: upstream reset"


def test_key_never_reaches_rows_or_logs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    echo = {"error": {"code": 401, "message": "Bad key"}}
    h = Harness(tmp_path, [httpx.ReadTimeout("slow"), httpx.Response(401, json=echo)])
    with caplog.at_level(logging.DEBUG), pytest.raises(NotAuthorised):
        h.call()
    assert "sk-test-secret" not in caplog.text
    assert all("sk-test-secret" not in repr(a) for a in h.log.attempts)


def test_retry_after_as_a_date(tmp_path: Path) -> None:
    when = email.utils.format_datetime(datetime.now(UTC) + timedelta(seconds=60), usegmt=True)
    h = Harness(tmp_path, [httpx.Response(503, headers={"Retry-After": when}), ok()])
    h.call()
    assert 50 < h.sleeps[0] <= 60


def test_cost_above_worst_case_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    h = Harness(tmp_path, [ok(cost=5.0)])
    h.call()
    assert "above its worst case" in caplog.text


def test_reply_cut_off_at_max_tokens_is_not_retried(tmp_path: Path) -> None:
    h = Harness(tmp_path, [ok(content='{"in_scope": tr', finish="length")])
    with pytest.raises(ModelCallError, match="max_tokens"):
        h.call()
    assert len(h.requests) == 1


@pytest.mark.parametrize("status", [400, 403, 404])
def test_client_errors_are_not_retried(tmp_path: Path, status: int) -> None:
    h = Harness(
        tmp_path, [httpx.Response(status, json={"error": {"code": status, "message": "no"}})]
    )
    with pytest.raises(ModelCallError, match=f"HTTP {status}: no"):
        h.call()
    assert len(h.requests) == 1
    assert h.log.attempts[0].http_status == status


@pytest.mark.parametrize(("status", "error"), [(401, NotAuthorised), (402, OutOfCredits)])
def test_key_and_credit_errors_stop_the_run(
    tmp_path: Path, status: int, error: type[Exception]
) -> None:
    h = Harness(tmp_path, [httpx.Response(status, json={"error": {"code": status}})])
    with pytest.raises(error):
        h.call()
    assert len(h.requests) == 1


def test_budget_refuses_before_sending(tmp_path: Path) -> None:
    h = Harness(tmp_path, [])
    h.budget = Decimal("0.0001")
    with pytest.raises(BudgetExceeded):
        h.call()
    assert h.requests == []
    [row] = h.log.attempts
    assert row.outcome is Outcome.REFUSED
    assert h.log.spent_usd(7, "triage") == 0


def test_budget_is_checked_again_before_a_retry(tmp_path: Path) -> None:
    h = Harness(tmp_path, [httpx.ReadTimeout("slow"), ok()])
    body = request_body(h.prompt, h.prompt.render(INPUTS))
    payload_cost = worst_case_cost(h.prompt, len(json.dumps(body, ensure_ascii=False).encode()))
    # Room for one attempt only: the timed-out attempt reported no cost, so its worst case counts.
    h.budget = payload_cost * Decimal("1.5")
    with pytest.raises(BudgetExceeded):
        h.call()
    assert len(h.requests) == 1
    assert [a.outcome for a in h.log.attempts] == [Outcome.ERROR, Outcome.REFUSED]


def test_spend_uses_reported_cost_or_worst_case(tmp_path: Path) -> None:
    h = Harness(tmp_path, [ok(cost=None), ok(cost=0.001)])
    h.call()
    h.call()
    first, _ = h.log.attempts
    assert first.cost_usd is None
    assert h.log.spent_usd(7, "triage") == first.max_cost_usd + Decimal("0.001")


@pytest.mark.parametrize("cost", [-1, True, "0.1"])
def test_unusable_costs_are_ignored(tmp_path: Path, cost: Any) -> None:
    h = Harness(tmp_path, [ok(cost=cost)])
    assert h.call().cost_usd is None


def test_unknown_stage_has_no_budget(tmp_path: Path) -> None:
    h = Harness(tmp_path, [])
    h.prompt = write_prompt(tmp_path, name="grader/grade")
    with pytest.raises(BudgetExceeded, match="No budget"):
        h.call()


def test_wrong_inputs_fail_before_anything_is_sent(tmp_path: Path) -> None:
    h = Harness(tmp_path, [])
    with h.client() as client, pytest.raises(PromptError):
        client.call(CallRequest(run_id=7, prompt=h.prompt, inputs={"title": "x"}))
    assert h.log.attempts == []


def test_worst_case_cost(tmp_path: Path) -> None:
    prompt = write_prompt(tmp_path)
    # (1000 bytes + 64 overhead) at $1/M, plus 1000 reply tokens at $4/M.
    assert worst_case_cost(prompt, 1000) == Decimal("0.001064") + Decimal("0.004")


def test_separate_reasoning_counts_in_worst_case(tmp_path: Path) -> None:
    prompt = write_prompt(
        tmp_path,
        prompt_settings=settings(reasoning={"max_tokens": 500, "counted_separately": True}),
    )
    assert worst_case_cost(prompt, 0) == Decimal(64) / 1_000_000 + Decimal(1500 * 4) / 1_000_000
