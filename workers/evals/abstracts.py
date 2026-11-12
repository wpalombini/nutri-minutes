"""Abstracts for the eval datasets.

A dataset may store a paper's abstract only when its licence is CC BY or CC0 (`CLAUDE.md`).
Every other abstract is fetched from Europe PMC by PMID with Scout's client and cached outside
the repo (ADR 0005). A paper whose abstract can't be found is an error that stops the eval,
never a lower score.

Run from `workers/` with `EUROPE_PMC_CONTACT` set:
- `uv run python -m evals.abstracts evals/triage/dataset.jsonl` fetches and caches every abstract
  the dataset doesn't store.
- Add `--store-open` to write the CC BY and CC0 abstracts into the dataset instead.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from pipeline.db.models import REUSABLE_LICENCE_CODES
from pipeline.europe_pmc import FIRST_CURSOR, EuropePmcClient, SearchPage
from pipeline.scout.normalise import ArticleValues, RecordError, normalise
from pipeline.scout.settings import client_settings_from_env

CACHE_DIR_ENV = "EVAL_CACHE_DIR"
BATCH_SIZE = 50
"""PMIDs per search request, which keeps the query short."""
_PMID = re.compile(r"[1-9][0-9]*")

type Row = dict[str, Any]


class AbstractError(Exception):
    """An abstract couldn't be found, so the eval can't run."""


class Searcher(Protocol):
    def search(self, query: str, cursor: str = FIRST_CURSOR) -> SearchPage: ...


type SearcherFactory = Callable[[], AbstractContextManager[Searcher]]


def default_cache_dir() -> Path:
    """`EVAL_CACHE_DIR`, or the user's cache directory. Keep it outside the repo."""
    configured = os.environ.get(CACHE_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    base = os.environ.get("XDG_CACHE_HOME", "").strip() or "~/.cache"
    return Path(base).expanduser() / "research-pipeline" / "abstracts"


def _checked_pmid(pmid: object) -> str:
    if not isinstance(pmid, str) or not _PMID.fullmatch(pmid):
        raise ValueError(f"Invalid PMID: {pmid!r}")
    return pmid


class AbstractCache:
    """One text file per PMID, so a cache entry can be read or removed by hand."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, pmid: str) -> Path:
        return self.directory / f"{_checked_pmid(pmid)}.txt"

    def get(self, pmid: str) -> str | None:
        try:
            text = self._path(pmid).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return text if text.strip() else None

    def put(self, pmid: str, abstract: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        _write_atomically(self._path(pmid), abstract)


def _write_atomically(path: Path, text: str) -> None:
    """Write then rename, so an interrupted write never leaves half a file."""
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as tmp:
        try:
            tmp.write(text)
        except BaseException:
            tmp.close()
            Path(tmp.name).unlink(missing_ok=True)
            raise
    Path(tmp.name).replace(path)


def _batches(items: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_records(searcher: Searcher, pmids: Iterable[str]) -> dict[str, ArticleValues]:
    """Europe PMC's PubMed records for these PMIDs, normalised as Scout stores them.

    PMIDs Europe PMC doesn't return are missing from the result.
    """
    wanted = list(dict.fromkeys(_checked_pmid(p) for p in pmids))
    found: dict[str, ArticleValues] = {}
    for batch in _batches(wanted, BATCH_SIZE):
        query = "SRC:MED AND (" + " OR ".join(f"EXT_ID:{pmid}" for pmid in batch) + ")"
        cursor: str | None = FIRST_CURSOR
        while cursor is not None:
            page = searcher.search(query, cursor)
            for record in page.records:
                try:
                    values = normalise(record)
                except RecordError as exc:
                    raise AbstractError(
                        f"Europe PMC returned a record we can't read: {exc}"
                    ) from exc
                if values.pmid is not None and values.pmid in batch:
                    found[values.pmid] = values
            cursor = page.next_cursor if page.records else None
    return found


def europe_pmc_searcher() -> AbstractContextManager[Searcher]:
    return EuropePmcClient(client_settings_from_env())


def resolve_abstracts(
    rows: Sequence[Row], cache: AbstractCache, searcher: SearcherFactory = europe_pmc_searcher
) -> dict[str, str]:
    """Every row's abstract by PMID: stored in the row, else cached, else fetched and cached.

    Europe PMC is only contacted when something is missing. Raises `AbstractError` if any
    abstract can't be found.
    """
    abstracts: dict[str, str] = {}
    missing: list[str] = []
    for row in rows:
        pmid = _checked_pmid(row["pmid"])
        stored = row.get("abstract")
        if stored is not None and row.get("licence") not in REUSABLE_LICENCE_CODES:
            raise AbstractError(f"PMID {pmid} stores an abstract but isn't CC BY or CC0")
        if isinstance(stored, str) and stored.strip():
            abstracts[pmid] = stored
        elif (cached := cache.get(pmid)) is not None:
            abstracts[pmid] = cached
        else:
            missing.append(pmid)
    if missing:
        with searcher() as client:
            records = fetch_records(client, missing)
        for pmid in missing:
            values = records.get(pmid)
            if values is not None and values.abstract:
                cache.put(pmid, values.abstract)
                abstracts[pmid] = values.abstract
    unresolved = [_checked_pmid(row["pmid"]) for row in rows if row["pmid"] not in abstracts]
    if unresolved:
        raise AbstractError(f"No abstract found for PMIDs {', '.join(unresolved)}")
    return abstracts


def read_dataset(path: Path) -> list[Row]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def write_dataset(path: Path, rows: Sequence[Row]) -> None:
    _write_atomically(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def store_open_abstracts(rows: Sequence[Row], searcher: Searcher) -> tuple[list[Row], list[str]]:
    """Rows with abstracts added where both the row and Europe PMC say CC BY or CC0.

    Returns the new rows and a problem line for each open row left without an abstract.
    """
    wanted = [
        row["pmid"]
        for row in rows
        if row["licence"] in REUSABLE_LICENCE_CODES and "abstract" not in row
    ]
    records = fetch_records(searcher, wanted) if wanted else {}
    problems: list[str] = []
    updated: list[Row] = []
    for row in rows:
        if row["pmid"] not in wanted:
            updated.append(row)
            continue
        values = records.get(row["pmid"])
        if values is None:
            problems.append(f"PMID {row['pmid']}: not found in Europe PMC")
        elif values.licence.licence_code not in REUSABLE_LICENCE_CODES:
            problems.append(
                f"PMID {row['pmid']}: Europe PMC now gives licence {values.licence.licence_code}"
            )
        elif not values.abstract:
            problems.append(f"PMID {row['pmid']}: Europe PMC has no abstract")
        else:
            row = {**row, "abstract": values.abstract}
        updated.append(row)
    return updated, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.abstracts", description=__doc__)
    parser.add_argument("dataset", type=Path, help="an eval dataset, one JSON object per line")
    parser.add_argument(
        "--store-open",
        action="store_true",
        help="write CC BY and CC0 abstracts into the dataset instead of caching",
    )
    args = parser.parse_args(argv)
    rows = read_dataset(args.dataset)

    if args.store_open:
        with europe_pmc_searcher() as client:
            updated, problems = store_open_abstracts(rows, client)
        added = sum(
            "abstract" in new and "abstract" not in old
            for new, old in zip(updated, rows, strict=True)
        )
        write_dataset(args.dataset, updated)
        print(f"Stored {added} abstracts in {args.dataset}")
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0

    cache = AbstractCache(default_cache_dir())
    try:
        resolve_abstracts(rows, cache)
    except AbstractError as exc:
        print(exc, file=sys.stderr)
        return 1
    stored = sum("abstract" in row for row in rows)
    print(
        f"All {len(rows)} abstracts available: {stored} stored, "
        f"the rest cached in {cache.directory}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
