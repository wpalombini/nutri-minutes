# "Why this grade"

An expandable section on the study page that explains the evidence grade: what raised and what lowered confidence. Closed by default, so the page stays short, and one keypress away.

## Content
- **Toggle:** "Why this grade is {level words, lower case}", for example "Why this grade is low certainty".
- **When open:**
  1. One sentence on the starting point, fixed by design category, so readers see why trials and observational studies start in different places:
     - Randomised trial: "Randomised trials start at high certainty, then move down for problems."
     - Review of studies: "A review starts from the certainty of the studies it combines, then moves up or down."
     - Observational study: "Observational studies start at low certainty, then move up or down."
     - Animal and lab studies: "Animal and lab studies start at very low certainty, because they don't test people."
     (These follow GRADE's usual starting points. The exact rules belong to the Evidence Grader; confirm the sentences match it before launch.)
  2. **"Raises confidence"** (plus icon) with its reasons.
  3. **"Lowers confidence"** (minus icon) with its reasons.
  4. A text link: "How we grade" (`/how-we-grade`).
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

    (+) Raises confidence                h3, type.interface-strong, plus icon
        - Size: 31,200 people, followed  list, type.body
          for 11 years.

    (-) Lowers confidence                h3, minus icon
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

Native `<details>` and `<summary>`: keyboard and screen-reader support for free, works with no JavaScript, and browsers that support it open it for find-in-page.

```html
<details class="why-grade" id="why-this-grade">
  <summary>
    <svg class="chevron" aria-hidden="true" …/>
    <h2>Why this grade is low certainty</h2>
  </summary>
  <div class="content">
    <p>Observational studies start at low certainty, then move up or down.</p>
    <h3><svg aria-hidden="true" …plus/>Raises confidence</h3>
    <ul>…</ul>
    <h3><svg aria-hidden="true" …minus/>Lowers confidence</h3>
    <ul>…</ul>
    <p><a href="/how-we-grade">How we grade</a></p>
  </div>
</details>
```

- The `h2` inside `<summary>` is valid HTML (summary allows one heading) and keeps the section in the page outline. Test it in NVDA and VoiceOver: some screen readers announce the summary as a button and not the heading. If heading navigation fails in testing, fall back to an `h2` containing a `<button aria-expanded aria-controls>` (the APG disclosure pattern) and render the content visible when JavaScript is off.
- Screen readers announce the state ("collapsed", "expanded") from `<summary>`; no `aria-expanded` is added by hand.
- Remove the default marker (`summary { list-style: none }` and `summary::-webkit-details-marker { display: none }`) and use the chevron.
- If the page is opened with `#why-this-grade`, open the details on load.
- The open state is not stored in the URL: it's a reading aid, not page state.

## Tokens
- Section: `border-block: border.divider-width solid border.divider`, `margin-block: space.40`.
- Summary: `display: flex; align-items: center; gap: space.12; min-block-size: target.primary; padding-block: space.12; cursor: pointer`. The `h2` inside: `type.interface-strong`, `text.primary`, `margin: 0`. The whole summary row is the target.
- Hover on the summary: the heading text gets an underline at `link.underline-width` (it's a control, so it reacts like one; no colour change).
- Focus: the standard ring on the `summary` (`:focus-visible`).
- Chevron: `inline-size` and `block-size` `space.16`, `color: icon.default`, `flex: none`. Points right when closed and down when open (`rotate: 90deg` on `details[open]`).
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
