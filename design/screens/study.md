# Study summary page

Route: `/studies/[id]`. Page title: "{headline} – Nutri Minutes".

## Purpose
Let a reader understand in under a minute what the study found, how sure we can be and what it does not show, then follow the source (PLAN section 1). Everything a reader needs for that is above the summary body: the finding as the headline, the grade, the design, and the result drawn to scale with its numbers.

## Content hierarchy
1. Topic link (where this sits).
2. Retraction or correction notice, if any.
3. **Headline** (`h1`): the finding, with its limits.
4. [Evidence grade](../components/evidence-grade.md) (full) and [study design label](../components/study-design-label.md). When the funder sells the product tested, a line follows them: "Funded by the maker of the product tested." It uses `type.meta` and `text.primary` and has no icon. It is plain text, not a warning, and comes before the interval.
5. [The interval](../components/interval.md), full size, with its caption.
6. "What the study found" (`h2`): the summary body.
7. ["What this study does not show"](../components/limits-block.md) (`h2`).
8. ["Why this grade is …"](../components/why-this-grade.md) (`h2`, expandable).
9. [Study at a glance](../components/study-at-a-glance.md) (`aside`, `h2`), with the DOI.

## Layout

### 360px

```
+--------------------------------+
| (header)                       |
+--------------------------------+
| Bone health                    |  topic, type.meta, text link
| More dairy linked to slightly  |  h1, type.headline-phone
| fewer hip fractures, but the   |
| range includes no difference   |
| [■][■][□][□] Low certainty,    |  grade (full)
| 2 of 4  (Observational study)  |  + design label
| Funded by the maker of the     |  funding line, if any
| product tested.                |
|                                |  space.40
| Hip fracture risk              |  the interval, full width
| Highest compared with lowest…  |
|          No difference         |
|  -------<===◆==|=>-----------  |
|  0.5             1          2  |  end and null labels only
|  Lower risk        Higher risk |
| Hip fracture risk was 9% lower |  caption
| … Hazard ratio 0.91, 95%       |
| confidence interval 0.80 to    |
| 1.04. The range includes 1, so |
| no difference is still         |
| plausible.                     |
|                                |  space.56
| What the study found           |  h2, type.section-heading
| (body, type.body)              |
| +- - - - - - - - - - - - - - -+|
| | What this study does not    ||  limits block
| | show                        ||
| +- - - - - - - - - - - - - - -+|
| > Why this grade is low        |  toggle, target.primary
|   certainty                    |
| +----------------------------+ |
| | Study at a glance          | |  the one raised panel
| | … Source (DOI link)        | |
| +----------------------------+ |
+--------------------------------+
| (footer with disclosure)       |
+--------------------------------+
```

### 1280px

```
+--------------------------------------------------------------------------+
| (header)                                                                 |
+--------------------------------------------------------------------------+
| Bone health                                                              |
| More dairy linked to slightly fewer hip fractures,                       |
| but the range includes no difference              h1, headline-desktop   |
| [■][■][□][□] Low certainty, 2 of 4   (Observational study)               |
| Funded by the maker of the product tested.                               |
|                                                                          |
| Hip fracture risk                                                        |
| Highest compared with lowest dairy intake                                |
|                               No difference                              |
|  ------------------<=====◆=====|==>------------------------------------  |
|  0.5          0.67             1             1.5                    2   |
|  Lower risk                                                Higher risk  |
|  Hip fracture risk was 9% lower … (caption, measure.caption)             |
|                                                                          |
| What the study found                          | +----------------------+ |
| (body, measure.body, in study-column-max)     | | Study at a glance    | |
|                                               | | Design               | |
| +- - - - - - - - - - - - - - - - - - - - - -+ | | People               | |
| | What this study does not show             | | | Followed for         | |
| +- - - - - - - - - - - - - - - - - - - - - -+ | | Main result          | |
|                                               | | Funding and conflicts| |
| > Why this grade is low certainty             | | …                    | |
|                                               | | Source (DOI link)    | |
|                                               | +----------------------+ |
+--------------------------------------------------------------------------+
| (footer with disclosure)                                                 |
+--------------------------------------------------------------------------+
```

### Rules
- **Top block** (topic to caption): full container width. The headline has no max width beyond the container, with `text-wrap: balance`; the interval uses the whole width, which is what makes it the bold element.
- **Below `breakpoint.960`:** one column: body, limits, why this grade, then the panel.
- **From `breakpoint.960`:** a two-column grid for the rest of the page: `grid-template-columns: minmax(0, layout.study-column-max) layout.study-panel; column-gap: layout.study-gap; justify-content: space-between; align-items: start`. The body, limits and "Why this grade" sit in **one wrapper** element, the grid's first child; the panel is the second. Each is one grid item, so a tall panel never opens gaps between the body's parts. The panel comes after the wrapper in the DOM at every width, so the reading order is the same on phones and desktops.
- Body prose `max-inline-size: measure.body` inside its column.

### Tokens and spacing
- Funding line: its own `<p>` after the grade and design line, `margin-block-start: space.4`.
- Topic: `type.meta`, a [text link](../components/links-and-buttons.md#text-link), in a `<p>` with hidden "Topic: " before it, `margin-block-end: space.8`.
- `h1`: `type.headline-phone` below 720px, `type.headline-desktop` from 720px, `text.primary`, `text-wrap: balance`, `margin-block-end: space.16`. Letter spacing in `em` per the tokens README.
- Grade and design line: flex, wrap, `column-gap: space.16`, `row-gap: space.4`.
- Interval: `margin-block-start: space.40`.
- Grid or column: `margin-block-start: space.56` below 720px, `space.72` from 720px.
- "What the study found": `h2` in `type.section-heading`, `margin-block-end: space.16`. Body `type.body`, paragraphs `space.16` apart. Body subheadings `h3` in `type.subheading`, `margin-block: space.40 space.8`.
- Panel below 960px: `margin-block-start: space.40`.

## Retraction and correction notices
Directly after the topic link and before the `h1`, so it's the first thing read.

```
(!) This study was retracted                 type.interface-strong, icon
    The journal retracted it on 3 March      type.interface
    2027. We keep this summary for the
    record, but don't rely on its findings.
    Read the retraction notice               text link
```

- A `<div role="note">` holding paragraphs, with no heading: a heading before the `h1` would break the heading order, and the notice is read first anyway because it comes first in the DOM. The first sentence is in `type.interface-strong`; the rest in `type.interface`, `text.primary`.
- Notice icon: `viewBox="0 0 16 16"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, `stroke-linecap="round"`: `<circle cx="8" cy="8" r="7"/><path d="M8 4.5v4.5M8 11.5v.01"/>`. `space.16` square, `icon.default`, `aria-hidden="true"`. The words carry the meaning.
- Layout: `display: grid; grid-template-columns: space.16 minmax(0, 1fr); column-gap: space.12; margin-block-end: space.24; max-inline-size: measure.caption`. No border, no fill, no colour: text and the icon only (dashed is for limits; filled is for the panel).
- **Retracted:** first line "This study was retracted", then "The journal retracted it on {date}. We keep this summary for the record, but don't rely on its findings." and a link "Read the retraction notice" (to the notice's DOI or PubMed record).
- **Correction published:** first line "The journal published a correction on {date}.", then "This summary has been checked against it." or "This summary hasn't been checked against it yet.", and a link "Read the correction". Which one shows depends on whether the pipeline re-checks summaries after a correction.
- **Summary updated:** no notice; the panel shows "Updated {date}". If the pipeline records what changed, add it there later.

## States

### Loading
Shell renders; main shows "Loading this summary…" ([shared loading state](app-shell.md#loading)).

### Not found
Unknown or unpublished ID: the [404 page](app-shell.md#page-not-found-404). An unpublished summary must be indistinguishable from one that never existed (the API reads published views only).

### Error
API failure or an invalid summary (no grade, design category, or DOI or PMID): the [error page](app-shell.md#error-the-page-couldnt-load). Never a partial page.

### Content variants
- **No interval reported:** the interval's [no-range state](../components/interval.md#states): no drawing, numbers in words, "The abstract doesn't report a range."
- **No effect size:** the figure is left out; the top block goes from the grade line straight to the body, with `space.40` before it.
- **Linear outcome:** the interval's difference scale, unit in the outcome line.
- **Animal or lab study:** the design label says so; the limits block starts with its fixed item.
- **Very long headline:** wraps; never truncated.

## Keyboard and screen readers
- Landmarks: banner, main, complementary ("Study at a glance"), contentinfo. The limits block is a named region. "Why this grade" is a plain section, not a region.
- Headings: `h1` headline; `h2` "What the study found", "What this study does not show", "Why this grade is …", "Study at a glance"; `h3` inside the body and inside "Why this grade".
- Tab order: skip link, wordmark, nav, topic link, (notice link), links in the caption if any, links in the body, the "Why this grade" toggle, links inside it when open, the DOI link, footer links.
- No live regions: nothing on this page updates after load.
- The figure is announced through its caption ([interval](../components/interval.md#structure)).

## Motion
The interval grows once on load ([interval motion](../components/interval.md#motion)); "Why this grade" fades in when opened. Nothing else. Both are removed under reduced motion.

## Metadata
- `<title>` and `og:title`: the headline + " – Nutri Minutes".
- Description: `result_sentence`, which states the result plainly.
- Canonical URL with the public ID.
- Don't add structured data that claims medical authority (no `MedicalWebPage`); `Article` with `citation` to the DOI (or the PubMed record) is fine.

## Data (a "summary")
Everything in the [summary list item](../components/finding-row.md#data-a-summary-list-item), plus:

| Field | Type | From |
|---|---|---|
| `effect` (full) | object or null | [Interval data](../components/interval.md#data): measure, scale, estimate, limits, level, unit, outcome and comparison labels, direction words, result and absolute sentences |
| `source_basis` | `abstract` or `full_text` | |
| `body` | structured blocks: paragraphs and `h3` subheadings, plain text with inline emphasis and links only; never raw HTML | Writer, fact-checked |
| `limits` | string[] | [Limits block](../components/limits-block.md#data) |
| `grade_reasons` | list | [Why this grade](../components/why-this-grade.md#data) |
| at-a-glance fields | | [Study at a glance](../components/study-at-a-glance.md#data) |
| `retraction` | `{ date, notice_url }` or null | Article relations (`retraction_in`) |
| `correction` | `{ date, notice_url, rechecked: boolean }` or null | Article relations (`erratum_in`) |
| `updated_on` | date or null | |
