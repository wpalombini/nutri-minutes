# Home: this week's findings

Route: `/`. Page title: "This week's findings – Nutri Minutes" (or "Latest findings – Nutri Minutes", see [heading rule](#heading-rule)).

## Purpose
Show what's new this week, with the most notable finding drawn in full, so a reader can see in seconds what was found and how sure we can be. Then let them browse by topic.

## Content hierarchy
1. `h1` "This week's findings" and the publication date.
2. **Lead finding:** the first finding of the edition, shown large: headline, topic, grade (full), design label and the full-size [interval](../components/interval.md) with its caption.
3. **The other findings** as [finding rows](../components/finding-row.md), in the edition's order.
4. "Browse by topic" (`h2`) with every topic as a [topic link](../components/links-and-buttons.md#topic-link).

The Editor chooses and orders the week's findings, so the first one is the lead. The page doesn't re-sort them.

## Heading rule
- If the latest edition was published in the last 7 days: `h1` "This week's findings".
- Otherwise: `h1` "Latest findings". It never says "this week" about older content.
- Under the `h1`, always: "Published {date}" in a `<time>`.
- The rule is worked out when the page renders, so a cached page keeps its heading until it is revalidated. If the page only revalidates when an edition is published, it will still say "This week" long after day 7. Revalidate on publish **and** on a time basis of at most a day, so the heading is wrong for no more than a day.

## Layout

### 360px

```
+--------------------------------+
| (header)                       |
+--------------------------------+
| This week's findings           |  h1, type.interface-strong
| Published 7 November 2026      |  type.meta, text.secondary
|                                |  space.32
| Twice-weekly balance classes   |  lead h2, type.headline-phone, headline link
| cut falls in adults over 70    |
| Falls and independence         |  topic, type.meta, text link
| [■][■][■][□] Moderate          |  grade (full) + design label
| certainty, 3 of 4              |
| (Randomised trial)             |
|                                |  space.32
| Number of falls                |  interval, full width
| Balance classes compared with  |
| usual care                     |
|          No difference         |
|  ------<====◆====>-|---------  |
|  0.5             1          2  |
|  Fewer falls        More falls |
| Falls were 23% less frequent…  |  caption
|                                |  space.56
|--------------------------------|  rows
| More dairy linked to slightly  |
| fewer hip fractures, but the   |
| range includes no difference   |
| Bone health                    |
| --<=◆=|>--  [■][■][□][□] Low   |
|             certainty          |
|             (Observational     |
|             study)             |
|--------------------------------|
| Protein at breakfast and leg   |
| strength in mice               |
| Muscle and strength with age   |
| --<==◆==>-  [■][□][□][□] Very  |
|             low certainty      |
|             (Animal study)     |
|--------------------------------|
|                                |  space.72
| Browse by topic                |  h2, type.section-heading
| [Bone health] [Muscle and      |  topic links, wrap
| strength with age] [Falls and  |
| independence] …                |
+--------------------------------+
| (footer with disclosure)       |
+--------------------------------+
```

### 1280px

```
+--------------------------------------------------------------------------+
| (header)                                                                 |
+--------------------------------------------------------------------------+
| This week's findings                                                     |
| Published 7 November 2026                                                |
|                                                                          |
| Twice-weekly balance classes cut         <- type.lead-headline,          |
| falls in adults over 70                     max study-column-max         |
| Falls and independence                                                   |
| [■][■][■][□] Moderate certainty, 3 of 4   (Randomised trial)             |
|                                                                          |
| Number of falls                                                          |
| Balance classes compared with usual care                                 |
|                               No difference                              |
|  ------------<=========◆=========>----------|------------------------   |
|  0.5          0.67             1             1.5                    2   |
|  Fewer falls                                                More falls  |
|  Falls were 23% less frequent … (caption, measure.caption)              |
|                                                                          |
|--------------------------------------------------------------------------|
| More dairy linked to slightly fewer      | --<=◆=|>-- | [■][■][□][□] Low |
| hip fractures, but the range includes    |            | certainty        |
| no difference                            |            | (Observational   |
| Bone health                              |            | study)           |
|--------------------------------------------------------------------------|
| Protein at breakfast and leg strength    | --<==◆==>- | [■][□][□][□] Very|
| in mice                                  |            | low certainty    |
| Muscle and strength with age             |            | (Animal study)   |
|--------------------------------------------------------------------------|
|                                                                          |
| Browse by topic                                                          |
| [Bone health] [Muscle and strength with age] [Falls and independence]    |
| [Heart and metabolism] [Brain health] [Longevity] [Genes and diet]       |
+--------------------------------------------------------------------------+
| (footer with disclosure)                                                 |
+--------------------------------------------------------------------------+
```

(Wireframe rows are narrowed to fit; real rows show the full labels, as in the [finding row](../components/finding-row.md) spec.)

## Structure

```html
<main id="main" tabindex="-1">
  <h1>This week's findings</h1>
  <p>Published <time datetime="2026-11-07">7 November 2026</time></p>

  <article class="lead" aria-labelledby="lead-heading">
    <h2 id="lead-heading"><a href="/studies/abc123">Twice-weekly balance classes…</a></h2>
    <p class="topic">…</p>
    <p class="meta">{grade, full} {design label}</p>
    <figure class="interval">…</figure>
  </article>

  <section aria-labelledby="more-heading">
    <h2 id="more-heading" class="visually-hidden">More findings this week</h2>
    <ul class="findings">…finding rows, each with an h3…</ul>
  </section>

  <section aria-labelledby="topics-heading">
    <h2 id="topics-heading">Browse by topic</h2>
    <ul class="topics">…topic links…</ul>
  </section>
</main>
```

- One `h1`. The lead finding is an `h2`. The other findings sit under a visually hidden `h2` "More findings this week" ("More recent findings" with the "Latest findings" heading), so each row's headline is an `h3` and screen-reader users get a clear outline: page, lead, more findings, topics.
- The lead's headline is the link to its study page. There's no extra "Read more" link.
- The `h1` is visually quiet on purpose: the lead headline is the visual hero, and the `h1` says what the page is.

## Tokens
- `h1`: `type.interface-strong`, `text.primary`, `margin: 0`. Date: `type.meta`, `text.secondary`, `margin-block-start: space.4`.
- Lead block: `margin-block-start: space.32`.
- Lead headline: `type.headline-phone` below 720px, `type.headline-desktop` from 720px, `type.lead-headline` from `breakpoint.960`; `text-wrap: balance`; `max-inline-size: layout.study-column-max`; a [headline link](../components/links-and-buttons.md#headline-link). Letter spacing in `em` per the tokens README.
- Lead topic: `type.meta` text link, `margin-block-start: space.8`. (The topic follows the headline here, as in rows, so the order is the same in every list.)
- Lead meta line: as on the study page (flex, wrap, `column-gap: space.16`), `margin-block-start: space.12`.
- Lead interval: full container width, `margin-block-start: space.32`. **No grow animation** on the home page: the plan keeps the one orchestrated moment for the study page.
- Rows section: `margin-block-start: space.56` below 720px, `space.72` from 720px.
- "Browse by topic": `h2` in `type.section-heading`, `margin-block: space.72 space.16`. Topic list `display: flex; flex-wrap: wrap; gap: space.12`.

## States

### Loading
Shell renders; main shows "Loading this week's findings…" ([shared loading state](app-shell.md#loading)).

### Empty: no edition yet
Before the first edition is published:

```
Findings
The first findings will be published soon.
Browse by topic   (topic links, if topics exist)
```

- `h1` "Findings", then a `<p>` in `type.body`: "The first findings will be published soon." No sign-up prompt in this version.
- "Browse by topic" stays if the topic list is available, so the page isn't a dead end.

### An edition with only one finding
The lead shows alone; the "More findings" section is left out, including its hidden heading.

### Lead without an interval
Use the interval's no-range or no-effect state. The lead stays the lead; the Editor chose it.

### Error
API failure: the [error page](app-shell.md#error-the-page-couldnt-load). If only the topic list fails but the edition loads, leave out "Browse by topic" and log it rather than failing the page; the nav still has "Topics".

### Invalid items
A finding with no grade, design category or DOI is left out ([conventions](README.md#content-rules-the-app-enforces)). If that's the lead, the next valid finding becomes the lead.

## Keyboard and screen readers
- Landmarks: banner, main, contentinfo. The two sections are named regions.
- Tab order: skip link, wordmark, nav, lead headline, lead topic, each row's headline then topic, topic links, footer links.
- No live regions.

## Motion
None on this page.

## Data
| Field | Type | Notes |
|---|---|---|
| `edition.published_on` | date | For the date line and the heading rule |
| `edition.findings` | ordered list | The first is the lead. Each is a [summary list item](../components/finding-row.md#data-a-summary-list-item); the lead also needs the full [interval fields](../components/interval.md#data) |
| `topics` | `{ name, slug }[]` | In the fixed editorial order (the order in the [topics spec](topics.md#topic-list)) |
