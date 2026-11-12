"""Eval abstracts: stored, cached or fetched, and stored in the repo only when openly licensed."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from evals.abstracts import (
    BATCH_SIZE,
    AbstractCache,
    AbstractError,
    Searcher,
    default_cache_dir,
    fetch_records,
    read_dataset,
    resolve_abstracts,
    store_open_abstracts,
    write_dataset,
)
from pipeline.europe_pmc import FIRST_CURSOR, SearchPage
from tests.records import record


class FakeSearcher:
    """Answers each query with the records whose PMID the query names, in pages of two."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.queries: list[str] = []

    def search(self, query: str, cursor: str = FIRST_CURSOR) -> SearchPage:
        self.queries.append(query)
        named = set(re.findall(r"EXT_ID:([0-9]+)", query))
        matches = [r for r in self.records if r["pmid"] in named]
        start = 0 if cursor == FIRST_CURSOR else int(cursor)
        page = matches[start : start + 2]
        more = start + 2 < len(matches)
        return SearchPage(page, str(start + 2) if more else None, len(matches))


def _factory(searcher: FakeSearcher) -> Any:
    @contextmanager
    def open_searcher() -> Iterator[Searcher]:
        yield searcher

    return open_searcher


def _row(pmid: str, licence: str = "cc-by-nc", **extra: Any) -> dict[str, Any]:
    return {"pmid": pmid, "licence": licence, "title": "A title.", **extra}


def _record(pmid: str, abstract: str | None = "An abstract.", licence: str = "cc by") -> Any:
    return record(id=pmid, pmid=pmid, doi=f"10.1000/{pmid}", abstractText=abstract, license=licence)


def test_default_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVAL_CACHE_DIR", str(tmp_path / "here"))
    assert default_cache_dir() == tmp_path / "here"
    monkeypatch.delenv("EVAL_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_cache_dir() == tmp_path / "research-pipeline" / "abstracts"


def test_cache_round_trip_and_rejects_bad_pmids(tmp_path: Path) -> None:
    cache = AbstractCache(tmp_path / "cache")
    assert cache.get("123") is None
    cache.put("123", "Text.")
    assert cache.get("123") == "Text."
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == ["123.txt"]
    with pytest.raises(ValueError, match="Invalid PMID"):
        cache.put("../x", "Text.")
    with pytest.raises(ValueError, match="Invalid PMID"):
        cache.get(123)  # type: ignore[arg-type]


def test_fetch_records_batches_and_pages() -> None:
    pmids = [str(1000 + i) for i in range(BATCH_SIZE + 3)]
    searcher = FakeSearcher([_record(p) for p in pmids] + [_record("999")])
    found = fetch_records(searcher, pmids)
    assert sorted(found) == sorted(pmids)
    assert all(q.startswith("SRC:MED AND (EXT_ID:") for q in searcher.queries)
    assert "EXT_ID:999" not in " ".join(searcher.queries)


def test_resolve_uses_stored_then_cache_then_fetch(tmp_path: Path) -> None:
    cache = AbstractCache(tmp_path)
    cache.put("2", "Cached.")
    searcher = FakeSearcher([_record("3", "Fetched.")])
    rows = [_row("1", "cc-by", abstract="Stored."), _row("2"), _row("3")]
    abstracts = resolve_abstracts(rows, cache, _factory(searcher))
    assert abstracts == {"1": "Stored.", "2": "Cached.", "3": "Fetched."}
    assert cache.get("3") == "Fetched."
    assert len(searcher.queries) == 1
    assert "EXT_ID:1" not in searcher.queries[0]
    assert "EXT_ID:2" not in searcher.queries[0]


def test_resolve_does_not_search_when_nothing_is_missing(tmp_path: Path) -> None:
    def fail() -> Any:
        raise AssertionError("searched")

    rows = [_row("1", "cc-by", abstract="Stored.")]
    assert resolve_abstracts(rows, AbstractCache(tmp_path), fail) == {"1": "Stored."}


def test_resolve_rejects_a_stored_abstract_without_an_open_licence(tmp_path: Path) -> None:
    rows = [_row("1", "cc-by-nc", abstract="Should not be here.")]
    with pytest.raises(AbstractError, match="isn't CC BY or CC0"):
        resolve_abstracts(rows, AbstractCache(tmp_path), _factory(FakeSearcher([])))


def test_resolve_fails_when_an_abstract_is_missing(tmp_path: Path) -> None:
    searcher = FakeSearcher([_record("1", abstract=None)])
    with pytest.raises(AbstractError, match="1, 2"):
        resolve_abstracts([_row("1"), _row("2")], AbstractCache(tmp_path), _factory(searcher))


def test_store_open_abstracts_only_for_open_licences() -> None:
    rows = [
        _row("1", "cc-by"),
        _row("2", "cc0"),
        _row("3", "cc-by-nc"),
        _row("4", "cc-by"),
        _row("5", "cc-by"),
        _row("6", "cc-by", abstract="Kept."),
    ]
    searcher = FakeSearcher(
        [
            _record("1", "One."),
            _record("2", "Two.", licence="cc0"),
            _record("3", "Three."),
            _record("4", "Four.", licence="cc by-nc"),
        ]
    )
    updated, problems = store_open_abstracts(rows, searcher)
    assert [row.get("abstract") for row in updated] == ["One.", "Two.", None, None, None, "Kept."]
    assert problems == [
        "PMID 4: Europe PMC now gives licence cc-by-nc",
        "PMID 5: not found in Europe PMC",
    ]
    assert "EXT_ID:3" not in " ".join(searcher.queries)
    assert "abstract" not in rows[0]


def test_dataset_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "dataset.jsonl"
    rows = [_row("1", note="Café"), _row("2")]
    write_dataset(path, rows)
    assert "Café" in path.read_text(encoding="utf-8")
    assert read_dataset(path) == rows
