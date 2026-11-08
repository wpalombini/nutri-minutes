# Links and buttons

Every interactive element in the MVP. Links go somewhere; buttons do something (`<a>` for navigation, `<button>` for actions, never a `<div>` with a click handler). Beetroot (`text.link`) means "go somewhere"; a solid outline means "control" (PLAN section 4).

Shared rules:
- Focus: the standard ring on `:focus-visible` (`focus.ring`, `focus.ring-width`, `focus.ring-offset`), on every variant, in every state. See [App shell](../screens/app-shell.md#focus).
- Hover never moves anything: no lift, no scale, no shadow. It thickens an underline or a border.
- Hover is not the only feedback: on touch, where there's no hover, the rest state already shows the element is interactive.
- Never `transition: all`. Border weight changes animate `box-shadow` over `motion.hover`; underline thickness changes are instant.
- Under `prefers-reduced-motion: reduce`, nothing animates.
- `touch-action: manipulation` on all of them.

## Text link

Inline links in prose, captions, the footer, the topic line in rows and the DOI.

| State | Treatment |
|---|---|
| Rest | `color: text.link`; `text-decoration: underline`; `text-decoration-thickness: link.underline-width`; `text-underline-offset: link.underline-offset` |
| Hover | `color: text.link-hover` (the same Beetroot); `text-decoration-thickness: link.underline-hover-width` |
| Focus | Ring, plus the rest underline |
| Visited | `color: text.link-visited` (the same Beetroot; the palette keeps one accent). Underline unchanged |
| Active (pressed) | Same as hover |
| Disabled | Not used. A link that can't go anywhere is plain text, not a link |

- Always underlined, so links never rely on colour (WCAG 1.4.1).
- Link text says where it goes ("How summaries are made", "Bone health"), never "click here" or "read more". No arrows appended.
- Pairs: `text.link` on `surface.page` 6.83 / 7.74 and on `surface.raised` 7.50 / 6.73 (light / dark).
- Inline targets may be smaller than 24px tall (WCAG 2.5.8 exempts links in a sentence). Standalone links (footer, topic line, "How we grade") get `min-block-size: target.min` with `display: inline-flex; align-items: center`.

## Headline link
Finding headlines in rows and on the home lead: the whole headline is the link.

| State | Treatment |
|---|---|
| Rest | `color: text.primary`; underline `link.underline-width` at `link.underline-offset`, `text-decoration-color: text.link` |
| Hover | Underline `link.underline-hover-width` |
| Focus | Ring |
| Visited | Unchanged |

The headline stays in Spruce ink so the list reads as headlines, not as a wall of accent colour; the Beetroot underline still marks it as a link without relying on colour alone (the underline is the cue). `text.link` is used here as a non-text mark against the page; its text pair (6.83 / 7.74) covers that.

## Navigation link
The three links in the header.

| State | Treatment |
|---|---|
| Rest | `type.interface`, `color: text.link`, no underline; `min-block-size: target.primary`, `display: inline-flex; align-items: center` |
| Hover | Underline at `link.underline-width`, `link.underline-offset` |
| Current (`aria-current`) | Permanent underline at `link.underline-hover-width`, same colour |
| Focus | Ring |
| Visited | Unchanged |

No underline at rest is acceptable here: the links are in the `nav` landmark, in the header, set apart from text, so their position identifies them, and the current page is marked by the underline as well as `aria-current`.

## Topic link
The "Browse by topic" links on the home page and the list on `/topics`: links styled as controls, because they're a set of choices.

| State | Treatment |
|---|---|
| Rest | `type.interface`, `color: text.link`, no underline; `border: border.control-width border.control-style border.control`; `border-radius: radius.control`; `padding-inline: space.16`; `min-block-size: target.primary`; inline-flex, centred vertically; background none |
| Hover | `border-color: border.control-hover`, and the extra width drawn inside with `box-shadow: inset 0 0 0 calc(border.control-hover-width − border.control-width) border.control-hover`, so the layout doesn't shift |
| Focus | Ring outside the outline (`focus.ring-offset`) |
| Visited | Unchanged |
| Disabled | Not used |

Pairs: `border.control` on the page 6.04 / 8.21, `border.control-hover` 13.24 / 14.64.

```
+--------------+  +------------------------------+
| Bone health  |  | Muscle and strength with age |
+--------------+  +------------------------------+
```

Laid out as a `<ul>` with `display: flex; flex-wrap: wrap; gap: space.12`.

## Primary button
For the one main action on a screen: "Try again" on the error page, and the skip link's visible style. There's at most one per screen.

| State | Treatment |
|---|---|
| Rest | `background: button.primary.bg`; `color: button.primary.text`; `type.interface-strong`; `border: none`; `border-radius: radius.control`; `padding-inline: space.24`; `min-block-size: target.primary`; inline-flex, centred |
| Hover | Label underlined at `link.underline-width`, `link.underline-offset` (the fill doesn't change: there's no second fill colour, and the underline is the site's hover cue) |
| Focus | Ring outside the fill; the offset gap is the page surface |
| Active (pressed) | Same as hover |
| Busy | If an action takes time: label changes to "{verb}ing…" ("Trying again…"), `aria-disabled="true"`, and a `role="status"` region repeats the text once. No spinner |
| Disabled | Avoid. If an action is unavailable, say why in text next to it. If one is ever needed: keep it focusable with `aria-disabled="true"` (not the `disabled` attribute, which removes it from the tab order and hides the reason), switch to the secondary style with `color: text.secondary` and `border-color: border.control`, `cursor: not-allowed`, and put the reason in text linked by `aria-describedby`. Never a dashed outline: dashed means limits |

Pairs: label `button.primary.text` on `button.primary.bg` 13.24 / 14.64; the fill against the page 13.24 / 14.64.

## Secondary button
For a second action next to a primary one (none in the MVP yet; specified so the first one is consistent).

| State | Treatment |
|---|---|
| Rest | `background: none`; `color: text.primary`; `type.interface-strong`; `border: border.control-width border.control-style border.control`; `border-radius: radius.control`; `padding-inline: space.24`; `min-block-size: target.primary` |
| Hover | Same as the topic link: `border.control-hover` with the inset extra width |
| Focus, active, busy, disabled | As the primary button |

## The "Why this grade" toggle
A `<summary>`, specified in [Why this grade](why-this-grade.md#tokens): full-width row, `target.primary` tall, heading text underlined on hover, standard ring.

## Data
None.
