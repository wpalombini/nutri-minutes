# "Why this grade"

An expandable section on the study page that explains the evidence grade: what raised and what lowered certainty. Closed by default, so the page stays short, and one keypress away.

## Content
- **Toggle:** "Why this grade is {level words, lower case}", for example "Why this grade is low certainty".
- **When open:**
  1. One sentence on the starting point, fixed by design category, so readers see why trials and observational studies start in different places:
     - Randomised trial: "Randomised trials start at high certainty, then move down for problems."
     - Review of studies: "A review starts from the certainty of the studies it combines, then moves up or down."
     - Observational study: "Observational studies start at low certainty, then move up or down."
     - Animal and lab studies: "Animal and lab studies start at very low certainty, because they don't test people."
     (These follow GRADE's usual starting points. The exact rules belong to the Evidence Grader; whether these sentences match it is in the [open questions](../OPEN-QUESTIONS.md).)
  2. **"Raises certainty"** (plus icon) with its reasons.
  3. **"Lowers certainty"** (minus icon) with its reasons.
  4. A text link: "How we grade" (`/how-we-grade`).
- "Certainty" replaces the plan's "Raises confidence" and "Lowers confidence" (PLAN section 5), so the section uses the same word as the grade itself (decision 1). This is a small change to the approved plan.
- Each reason names its factor, then says what we found: "**Size:** 31,200 people, followed for 11 years." Factors come from a fixed list: Design, Size, Duration, Population, Funding and conflicts.
- Both group headings always show. An empty group says "Nothing for this study."

## Wireframes

Closed, 360px and 1280px:

```
--------------------------------------  divider
 >  Why this grade is low certainty      toggle, type.interface-strong, min block size target.primary
--------------------------------------  divider
```

Open:

```
--------------------------------------
 v  Why this grade is low certainty
    Observational studies start at       type.body
    low certainty, then move up or down.

    (+) Raises certainty                  h3, type.interface-strong, plus icon
        - Size: 31,200 people, followed  list, type.body
          for 11 years.

    (-) Lowers certainty                  h3, minus icon
        - Design: dairy intake was       list
          self-reported once, at the
          start.
        - Funding and conflicts: funded
          in part by a dairy industry
          body.

    How we grade                         text link
--------------------------------------
```

## Structure

The [APG disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/): a `<button>` inside the `h2`, controlling the panel after it. Screen readers keep the heading for navigation and announce the button's state.

```html
<section class="why-grade" id="why-this-grade" aria-labelledby="why-grade-heading">
  <h2 id="why-grade-heading">
    <button type="button" aria-expanded="false" aria-controls="why-grade-panel">
      <svg class="chevron" aria-hidden="true" …/>
      Why this grade is low certainty
    </button>
  </h2>
  <div id="why-grade-panel" class="content">
    <p>Observational studies start at low certainty, then move up or down.</p>
    <h3><svg aria-hidden="true" …plus/>Raises certainty</h3>
    <ul>…</ul>
    <h3><svg aria-hidden="true" …minus/>Lowers certainty</h3>
    <ul>…</ul>
    <p><a href="/how-we-grade">How we grade</a></p>
  </div>
</section>
```

- Enter and Space toggle it (a native `<button>` does this). `aria-expanded` changes between `"false"` and `"true"`. Focus stays on the button.
- The button is the only content of the `h2`, so the heading's name is the button's text.
- **Without JavaScript the content must still be readable.** The server renders the panel without `hidden`. A small inline script in `<head>` adds a `js` class to `<html>` before first paint, and only under `.js` is the closed panel hidden (`.js .content:not(.open) { display: none }`). There's no flash and no layout shift, and without JavaScript the panel is simply open with the button doing nothing. The inline script needs a CSP hash, like any static inline script.
- If the page is opened with `#why-this-grade`, open the panel on load.
- The open state is not stored in the URL: it's a reading aid, not page state.
- Why not `<details>` and `<summary>`? HTML does allow a heading inside `<summary>`, but `<summary>` is exposed as a button and screen readers commonly drop the heading inside it, so the section disappears from heading navigation.

## Tokens
- Section: `border-block: border.divider-width solid border.divider`, `margin-block: space.40`.
- `h2`: `margin: 0`. Button: reset its native styles (`appearance: none; background: none; border: none; padding-inline: 0; inline-size: 100%; text-align: start`), then `display: flex; align-items: center; gap: space.12; min-block-size: target.primary; padding-block: space.12; cursor: pointer`, `type.interface-strong`, `color: text.primary`. The whole row is the target.
- Hover on the button: its text gets an underline at `link.underline-width`, instantly (it's a control, so it reacts like one; no colour change).
- Focus: the standard ring on the button (`:focus-visible`).
- Chevron: `inline-size` and `block-size` `space.16`, `color: icon.default`, `flex: none`. Points right when closed and down when open (`rotate: 90deg` when `aria-expanded="true"`).
- Content: `padding-block-end: space.24`, `padding-inline-start: calc(space.16 + space.12)` so it lines up with the heading text; `max-inline-size: measure.body`.
- Starting sentence: `type.body`, `text.primary`, `margin-block-end: space.24`.
- Group headings (`h3`): `type.interface-strong`, `text.primary`, `display: flex; align-items: center; gap: space.8; margin-block: space.24 space.8`. Icons `space.16` square, `icon.default` (13.24 / 14.64 on the page, light / dark).
- Reasons: `type.body`; the factor name in bold weight (`font.weight.semi-bold`, Literata) followed by a colon. List `padding-inline-start: space.24`, items `space.8` apart.
- "How we grade": a [text link](links-and-buttons.md#text-link), `type.interface`, `margin-block-start: space.24`.

## Icons
Original, drawn for this project (recorded in [`../ASSETS.md`](../ASSETS.md)). `viewBox="0 0 16 16"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"`:

| Icon | Path |
|---|---|
| Chevron (right) | `<path d="M6 3l5 5-5 5"/>` |
| Plus, in a circle | `<circle cx="8" cy="8" r="7"/><path d="M8 5v6M5 8h6"/>` |
| Minus, in a circle | `<circle cx="8" cy="8" r="7"/><path d="M5 8h6"/>` |

The plus and minus always sit next to their text headings; they are never the only cue.

## Motion
- Opening: the content fades in over `motion.expand` (`duration.200`, `easing.in-out`), `opacity` only. Height changes at once; it isn't animated, because height isn't a compositor property and the plan allows only `transform` and `opacity`.
- The chevron rotates over `motion.hover` (`duration.120`).
- Under `prefers-reduced-motion: reduce`, both are instant.

## States
- **Rendered with its page;** no loading state.
- **No reasons in either group:** each says "Nothing for this study." The section still shows, because every summary has a grade.
- **Grade missing:** the whole summary is invalid (see [conventions](../screens/README.md#content-rules-the-app-enforces)).

## Data

| Field | Type | Notes |
|---|---|---|
| `grade_level` | 1–4 | For the toggle text |
| `design_category` | enum | For the starting sentence |
| `grade_reasons` | `{ direction: 'raises' \| 'lowers', factor: 'design' \| 'size' \| 'duration' \| 'population' \| 'funding_and_conflicts', text: string }[]` | Fact-checked; factor names come from the app's fixed map |
