"""Client for the Europe PMC REST search API.

Requests use `resultType=core`, because the default `lite` results have no licence or abstract.
They never sort: sorted `cursorMark` requests returned 503 on every attempt in testing.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
FIRST_CURSOR = "*"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EuropePmcError(Exception):
    """A search request failed after its retries, or returned something unusable."""


@dataclass(frozen=True)
class SearchPage:
    records: list[dict[str, Any]]
    next_cursor: str | None
    hit_count: int


@dataclass(frozen=True)
class ClientSettings:
    contact: str
    """A project contact address or URL, sent in the User-Agent so EBI can get in touch."""
    request_delay_seconds: float = 1.0
    page_size: int = 200
    timeout_seconds: float = 30.0
    max_attempts: int = 5
    backoff_base_seconds: float = 2.0


def build_query(search_terms: str, window_start: date, window_end: date) -> str:
    """PubMed-indexed records first indexed within the window, inclusive."""
    return (
        f"({search_terms}) AND SRC:MED "
        f"AND FIRST_IDATE:[{window_start.isoformat()} TO {window_end.isoformat()}]"
    )


class EuropePmcClient:
    def __init__(
        self,
        settings: ClientSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not settings.contact.strip():
            raise ValueError("A contact address is required for Europe PMC requests")
        self._settings = settings
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._http = httpx.Client(
            transport=transport,
            timeout=settings.timeout_seconds,
            headers={"User-Agent": f"research-pipeline/0.1 (+{settings.contact.strip()})"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> EuropePmcClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search(self, query: str, cursor: str = FIRST_CURSOR) -> SearchPage:
        params: dict[str, str | int] = {
            "query": query,
            "resultType": "core",
            "format": "json",
            "pageSize": self._settings.page_size,
            "cursorMark": cursor,
        }
        body = self._get_json(params)
        try:
            records = body["resultList"]["result"]
            hit_count = int(body.get("hitCount", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise EuropePmcError("Unexpected search response shape") from exc
        if not isinstance(records, list):
            raise EuropePmcError("Unexpected search response shape")
        next_cursor = body.get("nextCursorMark")
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            next_cursor = None
        return SearchPage(records=records, next_cursor=next_cursor, hit_count=hit_count)

    def _wait_for_turn(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            remaining = self._settings.request_delay_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _get_json(self, params: dict[str, str | int]) -> dict[str, Any]:
        attempts = self._settings.max_attempts
        for attempt in range(1, attempts + 1):
            self._wait_for_turn()
            try:
                response = self._http.get(SEARCH_URL, params=params)
            except httpx.TransportError as exc:
                problem = f"{type(exc).__name__}"
            else:
                if response.status_code == 200:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise EuropePmcError("Search response was not JSON") from exc
                    if not isinstance(body, dict):
                        raise EuropePmcError("Unexpected search response shape")
                    return body
                if response.status_code not in RETRYABLE_STATUS:
                    raise EuropePmcError(f"Search request failed with HTTP {response.status_code}")
                problem = f"HTTP {response.status_code}"
            if attempt == attempts:
                raise EuropePmcError(f"Search request failed after {attempts} attempts: {problem}")
            backoff = self._settings.backoff_base_seconds * 2 ** (attempt - 1)
            logger.warning(
                "Europe PMC request failed (%s), retrying in %.0fs (attempt %d of %d)",
                problem,
                backoff,
                attempt,
                attempts,
            )
            self._sleep(backoff)
        raise AssertionError("unreachable")
