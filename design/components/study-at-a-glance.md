# Study at a glance

The facts of one study in one place, including the source. The only raised, filled panel on any page, so the raised surface always means "the facts of this study" (PLAN section 4, principle 8).

## Content, in order

| Label | Example | Notes |
|---|---|---|
| Design | Observational study (cohort) | The [design label](study-design-label.md) words without parentheses, plus the specific design from the paper in parentheses if given |
| People | 31,200 adults aged 50 to 83 in Sweden | Number and who |
| Followed for | 11 years | Left out for designs with no follow-up (lab studies) |
| Main result | Hazard ratio 0.91 (95% confidence interval 0.80 to 1.04) | Same formatting as the [interval caption](interval.md#the-caption); "No range reported" when there are no limits; row left out when there's no effect size |
| Funding and conflicts | Public research council; one author had received fees from a dairy company | |
| Journal | Journal name | |
| Paper published | 2 November 2026 | |
| Summary published | 7 November 2026 | Plus "Updated {date}" on a second line if it was |
| Summarised from | The abstract | "The abstract" or "The full text" |
| Licence | CC BY | Built from `licence_code` (below), never the raw value |
| Source | https://doi.org/10.xxxx/xxxxx | The DOI as a link. With no DOI, the PubMed record (https://pubmed.ncbi.nlm.nih.gov/{PMID}/) instead. Always present. |

**Licence labels** from `licence_code` in [`docs/database.md`](../../docs/database.md#article_licences): `cc0` "CC0", `cc-by` "CC BY", `cc-by-sa` "CC BY-SA", `cc-by-nc` "CC BY-NC", `cc-by-nd` "CC BY-ND", `cc-by-nc-sa` "CC BY-NC-SA", `cc-by-nc-nd` "CC BY-NC-ND", `other` "Other licence", `unknown` "Not stated". The code has no version, so the label has none.

**Changes to the plan:** the plan's panel lists Design, People, Followed for, Main result, Funding, Source and Licence. This spec renames Funding to "Funding and conflicts" (the grade weighs both) and adds Journal, Paper published, Summary published and Summarised from. The owner accepted these additions.

"Summarised from" and "Licence" together tell readers why some summaries quote less: we reuse full text only when the licence allows (`CLAUDE.md`, licensing).

## Wireframe

Same panel at both widths; only its place on the page changes (see [study page](../screens/study.md#layout)).

```
+----------------------------------+   surface.raised, radius.block, no border, no shadow
|  Study at a glance               |   h2, type.subheading
|                                  |
|  Design                          |   dt, type.meta, text.secondary
|  Observational study (cohort)    |   dd, type.interface, text.primary
|                                  |   space.16
|  People                          |
|  31,200 adults aged 50 to 83 in  |
|  Sweden                          |
|  …                               |
|  Source                          |
|  https://doi.org/10.1000/abc123  |   text link, wraps anywhere
+----------------------------------+
```

## Structure

```html
<aside class="glance" aria-labelledby="glance-heading">
  <h2 id="glance-heading">Study at a glance</h2>
  <dl>
    <div><dt>Design</dt><dd>Observational study (cohort)</dd></div>
    …
    <div><dt>Source</dt><dd><a href="https://doi.org/10.1000/abc123">https://doi.org/10.1000/abc123</a></dd></div>
  </dl>
</aside>
```

- An `<aside>` (complementary landmark) named "Study at a glance", so screen-reader users can jump straight to the facts and the source.
- A description list, each pair wrapped in a `<div>` (valid in `<dl>`) for spacing.
- The source link's text is the full URL (the DOI URL, or the PubMed record's URL when there is no DOI): descriptive, and what people copy. It opens in the same tab.

## Tokens
- Panel: `background: surface.raised`, `border-radius: radius.block`, `padding: space.24`. No border and no shadow: its edge against the page is low contrast by design and nothing relies on it (`surface.raised` description).
- Heading: `type.subheading`, `text.primary`, `margin: 0 0 space.16`.
- Pairs: `display: grid; gap: space.16` between pairs; inside a pair, `gap: space.4`.
- `dt`: `type.meta`, `text.secondary` (6.63 / 7.15 on raised, light / dark).
- `dd`: `type.interface`, `text.primary`, `margin: 0`. Numbers in the Main result, People and dates use tabular figures (`font-variant-numeric: tabular-nums`, as in `type.figures`) at the interface size.
- Source link: a [text link](links-and-buttons.md#text-link) on the raised surface (`text.link` 7.50 / 6.73), `overflow-wrap: anywhere` so a long DOI wraps instead of widening the page.
- Focus ring on the link: the offset gap is `surface.raised`, which the `focus.ring` pair covers.

## Layout
- **Below `breakpoint.960` (including 360px):** full width of the content column, after "Why this grade".
- **From `breakpoint.960` (including 1280px):** in the `layout.study-panel` column beside the summary, starting level with "What the study found". It scrolls with the page; it is never sticky.

## States
- **Rendered with its page;** no loading state.
- **Missing optional fields** (followed for, funding, journal): leave the row out. Licence always shows ("Not stated" when unknown), and so does Funding and conflicts. It shows "Not reported" when the study doesn't state its funding, or "Not stated in the abstract" when the summary was made from the abstract alone. It never shows "None" unless the study says so, because a missing funding statement is itself information.
- **No DOI:** link the PubMed record from the PMID. With neither, the summary is invalid (see [conventions](../screens/README.md#content-rules-the-app-enforces)).

## Motion
None.

## Data

| Field | Type |
|---|---|
| `design_category` | enum |
| `design_detail` | string or null ("cohort", "case-control", "crossover") |
| `population` | string |
| `follow_up` | string or null |
| `effect` | the [interval fields](interval.md#data) |
| `funding_and_conflicts` | string or null |
| `funding_basis` | `stated`, `not_reported` or `not_in_abstract` |
| `funder_sells_product` | boolean or null; when true, the study page shows the funding line next to the grade |
| `journal` | string or null |
| `paper_published_on` | date or null |
| `published_on`, `updated_on` | date, date or null |
| `source_basis` | `abstract` or `full_text` |
| `licence_code` | enum from `article_licences`, the current licence |
| `doi` | string or null, canonical (lowercase, no prefix), shown as `https://doi.org/{doi}` |
| `pmid` | string (digits) or null, shown as `https://pubmed.ncbi.nlm.nih.gov/{pmid}/` when there is no DOI. At least one of `doi` and `pmid` is required |
