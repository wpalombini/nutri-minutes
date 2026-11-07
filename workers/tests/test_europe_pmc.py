"""The Europe PMC client: request parameters, paging and retries."""

from datetime import date

import httpx
import pytest

from pipeline.europe_pmc import (
    ClientSettings,
    EuropePmcClient,
    EuropePmcError,
    build_query,
)
from tests.records import record, search_body


def _client(handler: httpx.MockTransport, sleeps: list[float]) -> EuropePmcClient:
    return EuropePmcClient(
        ClientSettings(contact="ops@example.org", request_delay_seconds=1.0, max_attempts=3),
        transport=handler,
        sleep=sleeps.append,
        clock=lambda: 0.0,
    )


def test_build_query() -> None:
    assert build_query("diet", date(2026, 10, 1), date(2026, 11, 7)) == (
        "(diet) AND SRC:MED AND FIRST_IDATE:[2026-10-01 TO 2026-11-07]"
    )


def test_search_sends_core_unsorted_request() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=search_body([record()], "next"))

    with _client(httpx.MockTransport(handle), []) as client:
        page = client.search("diet")
    params = seen[0].url.params
    assert params["resultType"] == "core"
    assert params["format"] == "json"
    assert params["cursorMark"] == "*"
    assert params["query"] == "diet"
    assert "sort" not in params
    assert seen[0].headers["User-Agent"] == "research-pipeline/0.1 (+ops@example.org)"
    assert page.next_cursor == "next"
    assert len(page.records) == 1


def test_unchanged_or_missing_cursor_ends_paging() -> None:
    bodies = [search_body([record()], "*"), search_body([], None)]

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=bodies.pop(0))

    with _client(httpx.MockTransport(handle), []) as client:
        assert client.search("diet").next_cursor is None
        assert client.search("diet", "abc").next_cursor is None


def test_retries_then_succeeds_with_backoff_and_delay() -> None:
    statuses = [503, 503, 200]
    sleeps: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        return httpx.Response(status, json=search_body([], None) if status == 200 else {})

    with _client(httpx.MockTransport(handle), sleeps) as client:
        client.search("diet")
    # Backoff of 2s then 4s; the 1s gap between requests is also waited for.
    assert [s for s in sleeps if s >= 2] == [2.0, 4.0]
    assert sleeps.count(1.0) == 2


def test_gives_up_after_max_attempts() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with _client(httpx.MockTransport(handle), []) as client, pytest.raises(EuropePmcError):
        client.search("diet")


def test_transport_errors_are_retried() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(200, json=search_body([], None))

    with _client(httpx.MockTransport(handle), []) as client:
        client.search("diet")
    assert calls == 2


def test_client_errors_are_not_retried() -> None:
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    with _client(httpx.MockTransport(handle), []) as client, pytest.raises(EuropePmcError):
        client.search("diet")
    assert calls == 1


@pytest.mark.parametrize("body", [{"resultList": {}}, {"resultList": {"result": "x"}}, []])
def test_unexpected_shapes_raise(body: object) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with _client(httpx.MockTransport(handle), []) as client, pytest.raises(EuropePmcError):
        client.search("diet")


def test_contact_is_required() -> None:
    with pytest.raises(ValueError, match="contact"):
        EuropePmcClient(ClientSettings(contact=" "))
