# Finding row

One summary in a list: its headline, topic, grade, design and a glyph of its main result. Used on the home page (all findings after the lead) and on topic archives. Rows, not cards (PLAN section 4).

## Content hierarchy
1. **Headline** (the finding, as a link to the study page).
2. **Topic** (a link to its archive). Left out on that topic's own archive page.
3. **Published date,** on topic archives only (on the home page every row is from the same week).
4. **Interval glyph,** or "No range reported" / "No effect size" / "Outside scale".
5. **Evidence grade** (compact) and **study design label,** plus "Retracted" if the study was retracted (see [states](#states)).

This is also the DOM order, at every width, so reading order, tab order and visual order always match.

Headlines are never truncated: they carry the limits of the finding ("…but the range includes no difference").

## Wireframes

360px: everything stacked in one column: text, then the glyph, then the grade and design label.

```
--------------------------------  divider
Twice-weekly balance classes cut   headline, type.finding-title, link
falls in adults over 70
Falls and independence             topic, type.meta, text link
                                   space.12
 --<==◆==>-|----                   glyph
[■][■][■][□] Moderate certainty    grade (compact)
(Randomised trial)                 design label, wraps if needed
--------------------------------  divider
```

1280px (from 720px): three columns: text, glyph, grade and design.

```
--------------------------------------------------------------------------------------
Twice-weekly balance classes cut falls in   |  --<==◆==>-|----  |  [■][■][■][□] Moderate certainty
adults over 70                              |                   |  (Randomised trial)
Falls and independence                      |                   |
--------------------------------------------------------------------------------------
```

## Structure

```html
<ul class="findings">          <!-- not <ol>: the order is editorial, not a sequence -->
  <li>
    <article aria-labelledby="f-abc123">
      <h3 id="f-abc123"><a href="/studies/abc123">Twice-weekly balance classes…</a></h3>
      <p class="topic"><span class="visually-hidden">Topic: </span><a href="/topics/falls-and-independence">Falls and independence</a></p>
      <p class="date">Published <time datetime="2026-11-07">7 November 2026</time></p>   <!-- archives only -->
      <div class="result">{glyph, aria-hidden}<span class="visually-hidden">Main result: …</span></div>
      <p class="meta">{evidence grade, compact} {study design label} {Retracted, if any}</p>
    </article>
  </li>
</ul>
```

- The headline's heading level is set by the page: `h3` on the home page (under a visually hidden `h2`) and on topic archives (under month `h2`s). The component takes it as a prop.
- Only the headline text is the link to the study, not the whole row: text stays selectable, and there are no nested links (the topic is a separate link).

## Tokens
- Row: `padding-block: space.24`; `border-block-end: border.divider-width solid border.divider`; the first row also has a top divider.
- Headline: `type.finding-title`, `text-wrap: balance`, `overflow-wrap: anywhere`, `margin: 0`. The link is a [headline link](links-and-buttons.md#headline-link).
- Topic: `type.meta`, a [text link](links-and-buttons.md#text-link), `margin-block-start: space.4`.
- Date: `type.meta`, `text.secondary`, `margin-block-start: space.4`.
- Result: the [glyph](interval.md#the-glyph-120px), or the "No range reported" / "No effect size" / "Outside scale" text in `type.meta`, `text.secondary`, `max-inline-size: data.interval-glyph-width`.
- Meta: `display: flex; flex-wrap: wrap; align-items: center; column-gap: space.16; row-gap: space.4`.

### Below 720px
One column, in DOM order: headline, topic, date, result, meta, each full width. The result and the meta each have `margin-block-start: space.12`. Putting the glyph and the meta side by side would leave the meta about 152px at 320px, narrower than "(Observational study)" (about 185px), so they stack. Inside the meta, the grade and the design label wrap onto separate lines when they don't fit.

### From 720px (and at 1280px)
`grid-template-columns: minmax(0, 1fr) data.interval-glyph-width max-content; column-gap: space.32; align-items: start`, with named areas:

```
"headline result meta"
"topic    result meta"
"date     result meta"
```

- The result is aligned with the headline's first line: `margin-block-start: space.4`.
- The meta column stacks grade above design label (`flex-direction: column; align-items: start`).

## Interaction
- Hover on the headline link thickens its underline. Nothing else in the row reacts: the row isn't a link.
- Focus ring on the headline link and the topic link, as everywhere.

## States
- **Retracted study:** after the design label, add the word "Retracted" in `type.meta-strong`, `text.primary`, preceded by the notice icon (`aria-hidden`; see [study page](../screens/study.md#retraction-and-correction-notices)). The headline stays as published.
- **No interval / no effect size:** the glyph column shows the text, as above.
- **Invalid summary** (no grade, design category, or DOI or PMID): the row is not rendered at all, and the list's count leaves it out.
- **Long content:** headlines and topic names of any length wrap.
- Loading, empty and error belong to the list's page ([home](../screens/home.md#states), [topics](../screens/topics.md#states)).

## Motion
None. No hover lift, no reveal on scroll.

## Data (a "summary list item")

| Field | Type | Notes |
|---|---|---|
| `public_id` | string | For the study URL |
| `headline` | string | The finding, sentence case |
| `topic` | `{ name, slug }` | Primary topic (no planned stage produces this yet; see the [open questions](../OPEN-QUESTIONS.md)) |
| `grade_level` | 1–4 | [Evidence grade](evidence-grade.md) |
| `design_category` | enum | [Study design label](study-design-label.md) |
| `effect` | object or null | `measure`, `scale`, `estimate`, `ci_lower`, `ci_upper`, `ci_level`, `unit` and `outcome_label`: the [interval](interval.md#data) fields the glyph and its hidden sentence need |
| `published_on` | date | When our summary was published |
| `retracted` | boolean | From the article's relations (`retraction_in`) |
| `doi` | string or null | Not shown in the row |
| `pmid` | string (digits) or null | Not shown in the row. A row with neither `doi` nor `pmid` is invalid |
