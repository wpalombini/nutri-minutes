# Theme control

Lets readers choose the colour theme: System (the default, following the device), Light or Dark. It sits at the end of the [footer](../screens/app-shell.md#footer) on every page.

## Decision: a native radio group, laid out as a row of outlined options

- **Native radio group (chosen):** `<fieldset>`, `<legend>` and three `<input type="radio">` with `<label>`s. The browser gives the semantics, the keyboard model (Tab to the group, arrow keys between options) and the announcement ("Dark, radio button, checked, 3 of 3") for free, with no ARIA. All three choices are visible at once, and the current one is shown without opening anything.
- **Segmented control:** the same look, but built from buttons with `aria-pressed` or a custom `role="radiogroup"`. It needs scripted arrow keys and roving focus to match what native radios already do. We take its look, not its build.
- **Select:** compact, but it hides the choices behind a second step, shows only the current one, and is fiddly on touch for three options.

The radios are drawn as outlined options in the style of the [topic link](links-and-buttons.md#topic-link), so the footer gains no new visual language: an outline means "control".

## Markup

```html
<fieldset class="theme-control" hidden>
  <legend>Colour theme</legend>
  <div class="options">
    <label><input type="radio" name="theme" value="system"> <span>System</span></label>
    <label><input type="radio" name="theme" value="light"> <span>Light</span></label>
    <label><input type="radio" name="theme" value="dark"> <span>Dark</span></label>
  </div>
</fieldset>
```

- **Group name:** the visible `<legend>` "Colour theme" names the group. No `aria-label` on top of it.
- **Labels:** exactly "System", "Light" and "Dark". No icons in this version. If icons are ever added, they sit before the word, are `aria-hidden="true"`, and never replace it.
- Order is System, Light, Dark: the default first.
- The whole label is the target, so a tap anywhere on the option selects it.
- The `hidden` attribute is removed by the component once it has read the stored choice (see [Without JavaScript](#without-javascript)).

## Layout

The legend sits on its own line above the options; the three options sit in one row. The row never wraps at 320px (three short words, about 240px together) but may wrap at 200% text size, which is fine.

360px, at the end of the footer:

```
| No advertising, sponsorship or |
| affiliate links.               |
|                                |  space.24
| Colour theme                   |  legend, type.meta, text.secondary
|                                |  space.8
| +--------+ +-------+ +------+  |  options, gap space.8,
| | System | | Light | | Dark |  |  each target.primary tall
| +--------+ +-------+ +------+  |
+--------------------------------+
```

1280px (from 720px): in the footer's first column, under the no-advertising line. The second column (the footer links) is unchanged.

```
| No advertising, sponsorship or affiliate links.                          |
|                                                                          |
| Colour theme                                                             |
| +--------+ +-------+ +------+                                            |
| | System | | Light | | Dark |  (System checked: filled)                  |
| +--------+ +-------+ +------+                                            |
+--------------------------------------------------------------------------+
```

## Tokens and states

- `fieldset`: no border, no padding, no margin (`min-inline-size: 0` so it can shrink). `margin-block-start: space.24` above it, from the no-advertising line.
- `legend`: `type.meta`, `text.secondary`, `padding: 0`, `margin-block-end: space.8`. It's a label, not a heading.
- Options row: `display: flex; flex-wrap: wrap; gap: space.8`.
- Each `input`: the [visually hidden](../screens/app-shell.md#visually-hidden-text) pattern. It stays in the tab order and in the accessibility tree; only the label is drawn. Never `display: none`.
- Each label's visible box (the `span`, or the label itself): `type.meta`, `display: inline-flex; align-items: center; min-block-size: target.primary; padding-inline: space.16`, `border: border.control-width border.control-style border.control`, `border-radius: radius.control`, `cursor: pointer`.

| State | Treatment |
|---|---|
| Default (unchecked) | `color: text.primary`; background none; `border-color: border.control` |
| Hover (unchecked) | `border-color: border.control-hover`, extra width drawn inside with `box-shadow: inset 0 0 0 calc(border.control-hover-width - border.control-width) border.control-hover`, as the topic link. Nothing moves |
| Checked | `background: button.primary.bg`; `color: button.primary.text`; `border-color: button.primary.bg`. Same type and weight as unchecked, so nothing shifts |
| Hover (checked) | Label underlined at `link.underline-width`, `link.underline-offset`, as the primary button. The fill doesn't change |
| Focus | The standard ring on the option that holds the focused input (`input:focus-visible + span`, or `label:has(:focus-visible)`): `outline: focus.ring-width focus.ring-style focus.ring; outline-offset: focus.ring-offset` |
| Checked and focused | Fill plus ring, the ring outside the fill on the page, as the primary button |
| Disabled | Not used |

- **Checked never relies on colour:** filled against outlined is a difference of fill and lightness, not hue, and the radio state is announced. It reads the same in greyscale.
- **Size:** `target.primary` (44px) tall although the control is not primary. It's small enough to cost nothing in the footer, and readers 50+ benefit. Widths are well over 24px; the `space.8` gap keeps targets from touching.
- **Pairs, all already recorded, light / dark:**
  - Unchecked label `text.primary` on `surface.page`: 13.24 / 14.64.
  - Legend `text.secondary` on `surface.page`: recorded for the footer text.
  - Unchecked outline `border.control` on the page: 6.04 / 8.21. Hover `border.control-hover`: 13.24 / 14.64.
  - Checked label `button.primary.text` on `button.primary.bg`: 13.24 / 14.64. The fill against the page: 13.24 / 14.64.
  - Ring `focus.ring` on `surface.page`: 5.62 / 8.57.
- **No new colours or tokens.**
- **Forced colours:** backgrounds are removed, so the checked fill would vanish. Under `@media (forced-colors: active)` the checked option sets `forced-color-adjust: none; background: Highlight; color: HighlightText; border-color: Highlight`. Unchecked options keep their outline (`ButtonText` by the system). The ring uses `outline`, so it survives.
- **Motion:** none, in every mode. No transition on fill, border or underline, and no cross-fade when the theme changes; the page switches in one frame. This also satisfies `prefers-reduced-motion: reduce` without a special case.

## Behaviour

- **Applies at once:** selecting an option (click, tap, arrow key, Space) changes the theme immediately. No "Apply" or "Save" button. Arrow keys selecting as they move is normal for radios and harmless here.
- **Focus stays put** on the option the reader chose. Nothing else on the page moves.
- **No live region.** The radio state change is announced by the screen reader, and the visual change is the whole page. No toast, no status message, no sound.
- **System** follows `prefers-color-scheme` live: if the device switches to dark at sunset, the page follows without a reload. This needs no script; it is the stylesheet's media query.
- **Light** and **Dark** override the device until the reader picks again.

### Storage: this device only
- `localStorage`, key `nm-theme`, value `light` or `dark`. Choosing System removes the key. Any other value is treated as System.
- No cookie: the server would need to read it, which would force dynamic rendering and break the static, cached pages (ADR 0003).
- Wrap every read and write in `try`/`catch`. If storage is blocked (some private modes), the choice still applies for this page view and the site falls back to System on the next load. No error is shown.
- Other open tabs on the same device follow the change through the `storage` event.

### Applied before first paint
A tiny inline script in `<head>`, before the stylesheet can paint, so there's no flash of the wrong theme:

1. Read `nm-theme` (in `try`/`catch`).
2. If it is `light` or `dark`, set `document.documentElement.dataset.theme` to it. Otherwise set nothing.

The existing CSP already allows inline scripts. The script does nothing else, has no dependencies and never throws.

### `color-scheme` and `theme-color`
- `color-scheme`: `light dark` on `:root` (System), `light` under `:root[data-theme="light"]`, `dark` under `:root[data-theme="dark"]`. This keeps scrollbars, form controls and the browser's own UI in the chosen theme.
- `theme-color`: the two `<meta name="theme-color">` tags from the [app shell](../screens/app-shell.md#document) stay as they are for System. With an override, both tags' `content` is set to the chosen theme's `surface.page` (`#EDF2EF` for Light, `#0E1C19` for Dark), so whichever media query matches shows the chosen colour. Back to System restores the original values. The head script does this if it runs after the tags; otherwise the component does it on mount and on every change.

### Without JavaScript
- The `<fieldset>` is rendered with `hidden`. The component removes `hidden` after it has read storage and checked the right option, so the control never shows a wrong choice and never appears when it can't work.
- With no JavaScript the control stays hidden, nothing is stored, and the site follows the system setting through the stylesheet alone.
- The control is the last thing in the footer, so revealing it moves nothing else on the page (no layout shift).
- The server can't know the stored choice, so the server HTML checks no option. The component checks one on mount (the stored one, or System). Read storage after mount, not during render, to avoid a hydration mismatch.

## How `data-theme` maps onto the tokens

The two existing colour files are used unchanged; only the generated selectors change. The token build emits:

```css
:root { /* light colour roles */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* dark colour roles */ }
}

:root[data-theme="dark"] { /* dark colour roles */ }
```

- No `data-theme`: the device decides (System).
- `data-theme="light"`: the light roles on `:root` win, and the dark media block doesn't apply.
- `data-theme="dark"`: the dark roles apply whatever the device says.
- The dark values are emitted twice, generated from the one dark file. Components still never test the theme themselves.

## Data
None. The control needs nothing from the API.

## Checks for the engineer
- With storage set to `dark` and the device in light, the first paint is dark (throttle the network and reload; no flash).
- System, then switch the device or Playwright's emulated scheme: the page follows without a reload.
- Tab reaches the group once; arrow keys move between options and apply each one; the ring is visible in both themes.
- A screen reader announces "Colour theme, group" and each option's name and state. Nothing else is announced on change.
- With JavaScript disabled, the control is absent and the page follows the system setting.
- In forced colours, the checked option is distinguishable.
- axe passes on the footer in Light, Dark and System, at 360px and 1280px.
