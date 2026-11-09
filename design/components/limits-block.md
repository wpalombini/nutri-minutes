# "What this study does not show"

The limits of a study, as first-class content in their own marked block, never a footnote (PLAN principle 3). On every study page, after the summary body.

## Purpose and content
1. Heading: "What this study does not show".
2. A list of short, plain statements, one limit each: "It can't show that dairy caused the lower risk.", "Most people in it were white women in Sweden, so it may not apply to everyone."
3. **A fixed first item for some designs,** added by the app from `design_category`, so the most important limit is never left out or softened:

| Design | Fixed first item |
|---|---|
| Observational study | "It can't show cause and effect. It found a link, and other differences between the people in it may explain that link." |
| Animal study | "It was done in animals. Results in animals often don't carry over to people." |
| Lab study | "It was done on cells or tissue in a lab, not in people." |
| Randomised trial, review | No fixed item |

The pipeline's own limits follow. Whether the writer should then avoid repeating the fixed item is in the [open questions](../OPEN-QUESTIONS.md).

## Wireframe

```
+- - - - - - - - - - - - - - - - - - - -+   dashed border.limits, radius.block
|  What this study does not show        |   h2, type.subheading
|                                       |   space.12
|  - It can't show cause and effect.    |   list, type.body
|    It found a link, and other         |
|    differences between the people in  |
|    it may explain that link.          |
|  - Most people in it were white women |
|    in Sweden, so it may not apply to  |
|    everyone.                          |
+- - - - - - - - - - - - - - - - - - - -+
```

Same shape at 360px and 1280px; it fills the reading column (`layout.study-column-max` from 960px, the full container width below).

## Structure

```html
<section class="limits" aria-labelledby="limits-heading">
  <h2 id="limits-heading">What this study does not show</h2>
  <ul>…</ul>
</section>
```

- A labelled `<section>`, so it appears in the landmark list as a region named "What this study does not show".
- An `h2` on the study page, at the same level as "What the study found".
- A `<ul>` with visible bullets, even for one item.

## Tokens
- Border: `border: border.limits-width border.limits-style border.limits`, `border-radius: radius.block`. Dashed means "absence or limits" (PLAN section 4); it carries meaning, so it uses `border.limits` (6.04 / 8.21 on the page, light / dark), not the decorative divider.
- No fill: the background stays `surface.page`. The only filled block on any page is the at-a-glance panel.
- Padding: `space.16` below 720px, `space.24` from 720px.
- Heading: `type.subheading`, `text.primary`, `margin: 0 0 space.12`. Sized as a subheading, not `type.section-heading`, so the block reads as part of the summary.
- List: `type.body`, `text.primary`, `padding-inline-start: space.24`, items separated by `space.8`, `max-inline-size: measure.body`.
- Spacing: `margin-block: space.40` around the block.

## States
- **Rendered with its page;** no loading state.
- **No limits from the pipeline:** for observational, animal and lab studies the fixed item still shows. For a randomised trial or review with no limits, the summary is incomplete: treat it as invalid, like a missing grade, and show the error page. (This is stricter than the content rules require; the owner accepted it.)
- **Long items:** wrap; no truncation, no "show more".

## Keyboard and screen readers
Nothing interactive unless an item contains a link (a text link). Screen readers reach it by heading or by region.

## Motion
None.

## Data

| Field | Type | Notes |
|---|---|---|
| `limits` | string[] | Fact-checked, in order |
| `design_category` | enum | For the fixed first item |
