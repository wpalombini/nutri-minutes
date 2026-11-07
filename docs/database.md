# Database

The Postgres schema: what each table holds and why. Change this document in the same PR as any migration. [ADR 0002](adr/0002-database-migrations-and-schema-growth.md) covers migration tooling and how the schema grows.

**Status:** no migrations exist yet. The tables below are the plan for the first migration, and they contain only what [Scout](agents.md#scout) needs.

## Overview

```mermaid
erDiagram
    articles ||--o{ article_licences : "has"
    pipeline_runs ||--o{ pipeline_run_errors : "records"

    articles {
        bigint id PK
        text doi
        text pmid
        text pmcid
        text title
    }
    article_licences {
        bigint id PK
        bigint article_id FK
        text licence_code
    }
    pipeline_runs {
        bigint id PK
        text agent
        text status
    }
    pipeline_run_errors {
        bigint id PK
        bigint run_id FK
        text source_record_id
    }
```

## Tables

### `articles`
One row per paper, whichever source it came from.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `bigint` identity | No | Primary key |
| `doi` | `text` | Yes | Stored in canonical form (see below) |
| `pmid` | `text` | Yes | Digits only |
| `pmcid` | `text` | Yes | `PMC` followed by digits. Often missing: 45 of 100 records in one recent sample had none. |
| `title` | `text` | No | |
| `abstract` | `text` | Yes | Some records have none: 6 of 100 in the same sample |
| `journal` | `text` | Yes | |
| `publication_types` | `text[]` | No | As supplied by the source. Defaults to empty. |
| `language` | `text` | Yes | |
| `published_on` | `date` | Yes | Europe PMC `firstPublicationDate` |
| `first_indexed_on` | `date` | Yes | Europe PMC `firstIndexDate` |
| `source` | `text` | No | Where the record came from, such as `europe_pmc` |
| `source_record` | `jsonb` | No | The record as last received, so fields can be derived again without refetching |
| `first_seen_at` | `timestamptz` | No | |
| `updated_at` | `timestamptz` | No | |

**Constraints:**
- `doi`, `pmid` and `pmcid` each have a unique index that ignores nulls.
- At least one of the three must be present.
- Check constraints enforce the identifier formats, so two spellings of one identifier can't become two articles.

**Canonical DOIs:** lowercase, with any `https://doi.org/`, `http://dx.doi.org/` or `doi:` prefix removed.

### `article_licences`
The licences we have seen for each article. Old rows are kept when a licence changes, so we can show what the licence was at any point.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `bigint` identity | No | Primary key |
| `article_id` | `bigint` | No | References `articles` |
| `source` | `text` | No | Where the licence information came from |
| `raw_value` | `text` | Yes | Exactly as supplied, such as `cc by-nc`. Null when the source gave none. |
| `licence_code` | `text` | No | Normalised value (see below) |
| `full_text_reuse_allowed` | `boolean` | No | Generated from `licence_code` |
| `first_seen_at` | `timestamptz` | No | |
| `last_seen_at` | `timestamptz` | No | |

**Writing and reading:**
- **Same licence seen again:** if `licence_code` and `raw_value` match the source's current row, only `last_seen_at` is updated.
- **Different licence:** anything else adds a new row, so a licence that changes and changes back is still recorded correctly.
- **Current licence:** for each source, it's the row with the latest `last_seen_at`.

**Constraints and indexes:**
- A check constraint limits `licence_code` to the values below.
- An index on `(article_id, source, last_seen_at)` finds the current licence.

**Licence codes:**

| `licence_code` | Full-text reuse |
|---|---|
| `cc0` | Allowed |
| `cc-by` | Allowed |
| `cc-by-sa` | Not allowed |
| `cc-by-nc` | Not allowed |
| `cc-by-nd` | Not allowed |
| `cc-by-nc-sa` | Not allowed |
| `cc-by-nc-nd` | Not allowed |
| `other` | Not allowed |
| `unknown` | Not allowed |

`full_text_reuse_allowed` fails closed: anything other than `cc0` or `cc-by` is not reusable, including a licence value we don't recognise, which is stored as `other`. `CC BY-SA` is excluded because its share-alike terms make it more restrictive than `CC BY`. All these papers can still be summarised in our own words from abstracts and metadata.

### `pipeline_runs`
One row per run of an agent. This is how a failed run resumes and how runs are monitored.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `bigint` identity | No | Primary key |
| `agent` | `text` | No | Such as `scout` |
| `status` | `text` | No | `running`, `succeeded`, `partial` or `failed` |
| `parameters` | `jsonb` | No | Inputs, such as the search terms and date window |
| `checkpoint` | `jsonb` | Yes | Progress for resuming, such as the Europe PMC cursor |
| `counts` | `jsonb` | No | Totals, such as articles fetched, inserted, updated and failed |
| `error` | `text` | Yes | Why the run failed, if it did |
| `started_at` | `timestamptz` | No | |
| `finished_at` | `timestamptz` | Yes | |

`partial` means the run finished, but some records failed.

**Constraints:**
- A check constraint limits `status` to the values above.
- A partial unique index allows only one `running` row per agent.

**Resuming:** a worker holds a Postgres advisory lock for its agent while it runs, and the lock is released if the process dies. A worker that takes the lock and finds a `running` row knows that run is dead, so it resumes in that row from its checkpoint.

### `pipeline_run_errors`
Records that failed during a run. One bad record doesn't stop the run, and it may have no usable identifiers, so this table doesn't reference `articles`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `bigint` identity | No | Primary key |
| `run_id` | `bigint` | No | References `pipeline_runs` |
| `source` | `text` | No | |
| `source_record_id` | `text` | Yes | The source's ID, if it can be read |
| `error` | `text` | No | Must not contain secrets |
| `raw_record` | `jsonb` | Yes | The record that failed |
| `created_at` | `timestamptz` | No | |

**Indexes:**
- An index on `run_id` finds a run's errors, because Postgres doesn't index foreign keys automatically.

## How Scout writes to these tables
**Matching:** Scout looks for an existing article by DOI, PMID or PMCID.
- **No match:** insert a new article.
- **One match:** update that article and fill in any missing identifiers.
- **Matches on two different articles, or a stored identifier that differs from the incoming one:** change nothing and record an error, so a person can decide. Automatic merging could corrupt the link between a claim and its source.

**Licences:** Scout records the licence in the same transaction as the article, so an article is never stored without one.

## Before adding a second source
These tables assume Europe PMC is the only source. Before PubMed or any other source is added, a migration must:
- Keep one raw record per source, so one source can't overwrite another's. `jsonb` can't hold PubMed's XML as received.
- Define how licences from different sources combine. The rule must fail closed: full-text reuse is allowed only if every source's current licence allows it.

## Tables to come
Each agent's or feature's tables are added by their own migration when it's built. Names and shapes will change.

| Agent or area | Will store |
|---|---|
| Triage and later agents | Each article's status per agent |
| Triage | Scope decisions and relevance scores |
| Evidence Grader | Evidence grades and their reasons |
| Extractor | Structured facts |
| Writer | Summary versions |
| Fact-Checker and Hype Detector | Checks and flags per summary version |
| Contradiction Tracker | Links between findings |
| Editor | Research packs |
| Script Writer, Audio Producer and Audio QA | Scripts, audio files and QA results |
| Publisher | Published items |
| Web app | Accounts and billing, with personal data limited to an email address and a Stripe customer reference |
| All LLM and TTS calls | Model, tokens, cost and latency per call |
