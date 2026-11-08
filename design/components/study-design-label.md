# Study design label

What kind of study it was, in words, on every summary. It's how observational and animal studies are labelled as such, independent of the grade (PLAN section 5, `CLAUDE.md` content rules).

## Content
A fixed vocabulary, in parentheses, sentence case:

| `design_category` | Label |
|---|---|
| `randomised_trial` | (Randomised trial) |
| `observational` | (Observational study) |
| `animal` | (Animal study) |
| `lab` | (Lab study) |
| `review` | (Review of studies) |

The app owns this map. It never shows free text from the API here, so a label can't be reworded into something softer.

## Structure

```html
<span class="design"><span class="visually-hidden">Study design: </span>(Observational study)</span>
```

- Plain text: no outline, no fill, no icon (a solid outline means a control).
- The parentheses are part of the text. Screen readers read "Study design: Observational study".

## Tokens
- `type.meta`, colour `text.primary`. Primary, not secondary, text: the label matters as much as the grade, and for animal and lab studies it changes how the finding should be read.
- The label may wrap between words ("(Observational" / "study)") when its column is narrow; it never overflows or truncates. At 320px, "(Observational study)" is wider than half the row, so rows put it on its own full-width line on phones (see [finding row](finding-row.md#below-720px)). Don't use `white-space: nowrap`.

## Layout
- In a row and on the study page it follows the [evidence grade](evidence-grade.md) on the same line, `column-gap: space.16`, wrapping below it when they don't fit.
- Same at 360px and 1280px.

## States
- **Missing or unknown category:** the summary is invalid (see [conventions](../screens/README.md#content-rules-the-app-enforces)). Never fall back to no label: a missing label would hide that a study was observational or in animals.

## Motion
None.

## Data

| Field | Type | Notes |
|---|---|---|
| `design_category` | enum | One of the five values above |
