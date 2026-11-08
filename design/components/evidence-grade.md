# Evidence grade

How sure we can be about a study's result, shown on every summary, in every list. PLAN section 5 and decision 1.

## Purpose and content
Three things at once, none of them colour:
1. **Marks:** four squares, filled for each level reached, outlined for the rest.
2. **Words:** the level name, always visible: "High certainty", "Moderate certainty", "Low certainty" or "Very low certainty".
3. **Position on the scale:** "2 of 4", in the full variant.

| Level | Marks | Words |
|---|---|---|
| 4 | ■■■■ | High certainty |
| 3 | ■■■□ | Moderate certainty |
| 2 | ■■□□ | Low certainty |
| 1 | ■□□□ | Very low certainty |

Every level uses the same colour, `grade.mark`. There is no green, amber or red, and no level 0.

## Variants

| Variant | Shows | Used in |
|---|---|---|
| Compact | Marks + level words | [Finding rows](finding-row.md) |
| Full | Marks + level words + "2 of 4" | Study page, home lead finding |

```
Compact:  [■][■][□][□]  Low certainty
Full:     [■][■][□][□]  Low certainty, 2 of 4
```

## Structure

```html
<p class="grade">
  <span class="marks" aria-hidden="true"><span class="on"></span><span class="on"></span><span></span><span></span></span>
  <span class="visually-hidden">Evidence grade: </span>
  <span class="level">Low certainty</span><span class="position">, 2 of 4</span>
</p>
```

- The marks are `aria-hidden`; the text carries the meaning. A screen reader reads "Evidence grade: Low certainty, 2 of 4" (full) or "Evidence grade: Low certainty" (compact).
- It is text, not a link or a control. On the study page, the [Why this grade](why-this-grade.md) section explains it.
- Use `<p>` when it stands alone, or `<span>` with the same inner structure inside a row's metadata line.

## Tokens
- Wrapper: `display: inline-flex; align-items: center; flex-wrap: wrap; column-gap: space.8; row-gap: space.4`.
- Marks: `display: inline-flex; gap: grade.mark-gap; flex: none`. Each square `inline-size` and `block-size` `grade.mark-size`, `border-radius: radius.mark`, `border: grade.mark-border-width solid grade.mark`, `box-sizing: border-box`. Filled squares add `background: grade.mark`. Unfilled squares have no background, so the page or raised surface shows through.
- Level words: `type.meta-strong`, `text.primary`.
- ", 2 of 4": `type.meta`, `text.secondary`, with tabular figures from `type.figures` (it sits with other numbers).
- Contrast: `grade.mark` 13.24 / 14.64 on the page and 14.55 / 12.74 on the raised surface (light / dark). The level words are `text.primary`, recorded on both.

## Layout at 360px and 1280px
Same at every width. The marks never separate from each other; the words wrap after the marks if needed (at 320px with 200% text, "Very low certainty, 1 of 4" can wrap below the marks). Next to a [study design label](study-design-label.md), the two sit on one line when they fit, with `column-gap: space.16`, and wrap otherwise; the grade always comes first.

## States
- **Rendered with its page;** no loading state.
- **Missing or out-of-range level:** never render a guessed grade. The summary is invalid and is left out of lists or replaced by the error page (see [conventions](../screens/README.md#content-rules-the-app-enforces)).

## Forced colours
In `@media (forced-colors: active)`: `forced-color-adjust: none` on the marks; borders `CanvasText`; filled squares `background: CanvasText`. Without this the fill vanishes and every grade looks like level 0.

## Motion
None.

## Data

| Field | Type | Notes |
|---|---|---|
| `grade_level` | integer 1–4 | 4 is High. The words come from the app's own fixed map, not from free text, so they're always one of the four |

## Copy rules
- Always "certainty", never "quality", "strength" or "confidence" on its own, to match GRADE's terms (decision 1).
- "2 of 4", never "2/4".
