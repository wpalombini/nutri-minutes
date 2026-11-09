# Topics and topic archive

Two routes:
- `/topics`: the list of topics. Page title "Topics – Nutri Minutes".
- `/topics/[topic]`: one topic's archive of summaries, newest first. Page title "{Topic name} – Nutri Minutes", plus ", page {n}" after page 1.

## Topic list
The scope in `CLAUDE.md`, as seven topics, in this order:

| Name | Slug |
|---|---|
| Bone health | `bone-health` |
| Muscle and strength with age | `muscle-and-strength` |
| Falls and independence | `falls-and-independence` |
| Heart and metabolism | `heart-and-metabolism` |
| Brain health | `brain-health` |
| Longevity | `longevity` |
| Genes and diet | `genes-and-diet` |

The list comes from the API so it can change without a release, but the app expects names and slugs like these. Each topic also has a one-sentence description of what it covers. The descriptions in the wireframes are samples; the real ones will be drafted for the owner to approve. Where descriptions and counts come from is in the [open questions](../OPEN-QUESTIONS.md). The seven topics don't cover every nutrition study in scope; that gap is listed there too.

## `/topics`

### Purpose
Show every topic, what it covers and how many summaries it has, so readers can pick one.

### Layout

360px:

```
+--------------------------------+
| Topics                         |  h1
|                                |
|--------------------------------|
| Bone health                    |  h2 link, type.finding-title
| Diet, exercise and bone        |  description, type.interface,
| density, fractures and         |  text.secondary
| osteoporosis.                  |
| 12 summaries                   |  type.meta, text.secondary
|--------------------------------|
| Muscle and strength with age   |
| …                              |
+--------------------------------+
```

1280px: the same single list, the text within `measure.body`. A grid of cards would be the generic default, and seven items don't need it.

```
+--------------------------------------------------------------------------+
| Topics                                                                   |
|--------------------------------------------------------------------------|
| Bone health                                                              |
| Diet, exercise and bone density, fractures and osteoporosis.             |
| 12 summaries                                                             |
|--------------------------------------------------------------------------|
| …                                                                        |
+--------------------------------------------------------------------------+
```

### Structure and tokens
- `h1` "Topics": `type.headline-phone` below 720px, `type.headline-desktop` from 720px, `margin-block-end: space.32`.
- A `<ul>` of rows. Each row: `padding-block: space.24`, dividers as in [finding rows](../components/finding-row.md#tokens).
- Topic name: `h2` in `type.finding-title` containing a [headline link](../components/links-and-buttons.md#headline-link).
- Description: `type.interface`, `text.secondary`, `margin-block-start: space.4`, `max-inline-size: measure.body`.
- Count: `type.meta`, `text.secondary`, tabular figures, `margin-block-start: space.4`. "1 summary", "12 summaries", and "No summaries yet" for 0 (via `Intl.PluralRules('en-AU')`).

### States
- **Loading:** "Loading topics…".
- **Error:** the error page.
- **Empty list** (no topics returned): treat as an error; the site always has topics.

## `/topics/[topic]`

### Purpose
Every published summary in one topic, newest first, scannable by headline, grade and design.

### Content hierarchy
1. `h1`: the topic name.
2. The topic's description and the count ("12 summaries").
3. Summaries grouped by the month our summary was published, newest first: `h2` "November 2026", then [finding rows](../components/finding-row.md) with `h3` headlines, the topic line left out and the date shown.
4. Pagination, when there are more than 20.

### Layout

360px:

```
+--------------------------------+
| Topics                         |  link back, type.meta, text link
| Bone health                    |  h1
| Diet, exercise and bone        |  description, type.interface,
| density, fractures and         |  text.secondary
| osteoporosis.                  |
| 12 summaries                   |  type.meta, text.secondary
|                                |  space.40
| November 2026                  |  h2, type.subheading
|--------------------------------|
| More dairy linked to slightly  |  finding row (h3), no topic line
| fewer hip fractures, but the   |
| range includes no difference   |
| Published 7 November 2026      |
| --<=◆=|>--  [■][■][□][□] Low   |
|             certainty          |
|             (Observational     |
|             study)             |
|--------------------------------|
| …                              |
|                                |
| October 2026                   |
| …                              |
|                                |  space.56
| [Newer summaries] [Older       |  pagination, secondary-style links
| summaries]                     |
| Page 2 of 3                    |
+--------------------------------+
```

1280px: the same, with rows in their three-column form across the full container.

```
+--------------------------------------------------------------------------+
| Topics                                                                   |
| Bone health                                                h1            |
| Diet, exercise and bone density, fractures and osteoporosis.             |
| 12 summaries                                                             |
|                                                                          |
| November 2026                                                            |
|--------------------------------------------------------------------------|
| More dairy linked to slightly fewer hip  | --<=◆=|>-- | [■][■][□][□] Low |
| fractures, but the range includes no     |            | certainty        |
| difference                               |            | (Observational   |
| Published 7 November 2026                |            | study)           |
|--------------------------------------------------------------------------|
| …                                                                        |
|                                                                          |
| [Newer summaries]  [Older summaries]   Page 2 of 3                       |
+--------------------------------------------------------------------------+
```

### Structure and tokens
- "Topics" link to `/topics` above the `h1`: `type.meta`, a [text link](../components/links-and-buttons.md#text-link), `margin-block-end: space.8`. It's a plain link, not a breadcrumb trail, so it needs no `nav`.
- `h1`: as on `/topics`, `text-wrap: balance`.
- Description: `type.interface`, `text.secondary`, `max-inline-size: measure.body`, `margin-block-start: space.8`. Count as on `/topics`, `margin-block-start: space.4`.
- Month groups: a plain `<section>` with no accessible name, so it isn't exposed as a region and the landmark list stays short; `h2` in `type.subheading`, `margin-block: space.40 space.8`. Months in `Intl.DateTimeFormat('en-AU', { month: 'long', year: 'numeric' })`.
- Rows: the finding row with `headingLevel=3`, `showTopic=false`, `showDate=true`.
- A month that spans two pages repeats its heading on the second page.

### Pagination
- 20 summaries per page. URLs: `/topics/bone-health` for page 1, `?page=2` onwards. `?page=1` redirects to the bare URL. A page past the end, or a value that isn't a whole number from 2 up, is a 404.
- A `<nav aria-label="Pages">` after the last group, `margin-block-start: space.56`:
  - "Newer summaries" (to the previous page) and "Older summaries" (to the next page), as [topic-link styled](../components/links-and-buttons.md#topic-link) links (outlined controls, `target.primary` tall), `display: flex; flex-wrap: wrap; gap: space.12`. A link that doesn't apply (no newer on page 1, no older on the last page) is left out, not disabled.
  - "Page 2 of 3" in `type.meta`, `text.secondary`, after the links.
- No numbered page list: with at most a few pages per topic, newer and older are enough. Revisit if a topic passes about 10 pages.
- Following a pagination link is a route change, so focus moves to the `h1` ([App shell](app-shell.md#focus)); the `h1` stays the topic name, and the page title says the page number.

### States
- **Loading:** "Loading {topic name}…".
- **Unknown topic slug:** the 404 page.
- **Empty topic:** after the description, "No summaries in this topic yet." in `type.body`, then a text link "See this week's findings" (`/`). The count line reads "No summaries yet".
- **Error:** the error page.
- **Invalid items** are left out, and the count comes from the API's count of valid published items, so it matches what's shown. (If the API can't guarantee that, drop the count rather than show a wrong number.)

### Keyboard and screen readers
- Landmarks: banner, main, the "Pages" navigation, contentinfo.
- Headings: `h1` topic, `h2` months, `h3` summary headlines.
- Tab order: skip link, header, "Topics" link, each row's headline, pagination links, footer.
- No live regions; pagination is a full navigation, not an in-place update.

### Motion
None.

## Data

| Field | Type | Notes |
|---|---|---|
| `topics[]` | `{ name, slug, description, summary_count }` | For `/topics`, in order |
| `topic` | `{ name, slug, description, summary_count }` | For the archive header |
| `page`, `page_count` | integers | |
| `items` | [summary list item](../components/finding-row.md#data-a-summary-list-item)[] | Newest first by `published_on`, 20 per page |
