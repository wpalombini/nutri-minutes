# App shell

The frame around every page: skip link, header, main and footer. It is built first and everything else sits inside it, so this spec is the most exact. It also covers the shared page states: the prose page template, loading, 404 and error.

## Purpose
- Get readers to the content fast: one skip link, three navigation links, no sticky bars, nothing in front of the content.
- Carry the disclosure on every page, calmly, in the footer.
- Set the base for type, colour scheme and focus that every component relies on.

## Document

```html
<html lang="en-AU">
  <body>
    <a class="skip-link" href="#main">Skip to main content</a>
    <header>…wordmark, <nav aria-label="Main">…</nav></header>
    <main id="main" tabindex="-1">…page content…</main>
    <footer>…disclosure, footer links, theme control…</footer>
  </body>
</html>
```

- One `<header>` (banner landmark), one `<nav aria-label="Main">`, one `<main>`, one `<footer>` (contentinfo landmark). No other landmarks in the shell. Pages may add an `<aside>` (the study page does) and labelled `<section>`s.
- `lang="en-AU"`.
- `<meta name="viewport" content="width=device-width, initial-scale=1">`. Never `maximum-scale` or `user-scalable=no`.
- `color-scheme` set by each generated colour block (`light` in the light block, `dark` in the dark blocks), and `<meta name="theme-color">` twice, one per scheme, matching `surface.page`: `#EDF2EF` with `media="(prefers-color-scheme: light)"` and `#0E1C19` with `media="(prefers-color-scheme: dark)"`, through Next.js's `viewport` export (see [`icons/README.md`](../icons/README.md#using-it-in-the-web-app-nextjs-app-router)). The [theme control](../components/theme-control.md) narrows both when the reader picks Light or Dark.
- `<html>` has `suppressHydrationWarning`. One tiny inline script, a plain `<script>` in `<head>` of the server root layout, applies a stored theme before first paint ([theme control](../components/theme-control.md#applied-before-first-paint)).
- `body`: background `surface.page`, colour `text.primary`, `type.interface` as the default text style, `font-optical-sizing: auto` (Literata's optical size axis) and `-webkit-text-size-adjust: 100%`.
- `<title>`: "{page title} – Nutri Minutes" with an en dash, for example "Page not found – Nutri Minutes". Each spec gives its page title. Every page has exactly one `h1`.

## Layout and widths

One container is used by the header, main and footer, so their left edges line up:

- `max-width: calc(layout.content-max + 2 × gutter)`, centred with `margin-inline: auto`. Everything inside it is left-aligned.
- `padding-inline: layout.gutter` below 720px, `layout.gutter-wide` from `breakpoint.720`.
- Add `env(safe-area-inset-left)` and `env(safe-area-inset-right)` to the gutters (`max()` of the two), because the manifest allows standalone display.

Inside `main`, pages choose their own widths from these roles only:

| Width | Token | Used for |
|---|---|---|
| Full container | `layout.content-max` | Home rows, the interval, the study page top block, the footer |
| Reading column | `layout.study-column-max` | Study summary column; home lead headline |
| Body measure | `measure.body` (66ch) | Any running prose (summary body, prose pages) |
| Caption measure | `measure.caption` (62ch) | Interval captions, notes, the footer disclosure |
| Panel | `layout.study-panel` | Study at a glance, from `breakpoint.960` |

`main` has `padding-block: space.40 space.72` below 720px and `space.56 space.96` from 720px. Nothing in the shell is sticky or fixed.

## Skip link

- The first focusable element on every page. Text: "Skip to main content". `href="#main"`.
- Hidden with the [visually hidden](#visually-hidden-text) pattern until it has focus. On `:focus`, it becomes visible: positioned absolutely at `inset-block-start: space.8`, `inset-inline-start` equal to the gutter, above everything else (`z-index` above the header), styled as a [primary button](../components/links-and-buttons.md#primary-button) with the focus ring.
- `main` has `id="main"` and `tabindex="-1"`, so activating the link moves focus there and the next Tab goes to the first link inside main. `main` shows no ring when focused this way (`main:focus { outline: none }`): it isn't a control, and the ring would surround the whole page.
- It shows on `:focus`, not only `:focus-visible`, so it appears for every keyboard and switch user.

## Header

### Content
1. **Wordmark:** "Nutri Minutes" as text, a link to `/`. No logo or icon for now.
2. **Main navigation**, three links, in this order:
   - "This week" → `/`
   - "Topics" → `/topics`
   - "How we grade" → `/how-we-grade`

### Wireframes

360px: two rows. The nav wraps onto a third row only at large text sizes.

```
+--------------------------------+
| Nutri Minutes                  |  wordmark, type.subheading
|                                |  space.8
| This week  Topics  How we grade|  nav, type.interface, gap space.24
+--------------------------------+  divider
```

1280px (and from 720px): one row, wordmark left, nav right.

```
+--------------------------------------------------------------------------+
| Nutri Minutes                          This week   Topics   How we grade |
+--------------------------------------------------------------------------+
```

### Tokens
- Header: `padding-block: space.16` below 720px, `space.24` from 720px. Bottom border `border.divider-width` solid `border.divider`, spanning the full viewport width (the border sits on the full-width `<header>`, the content on the container inside it).
- Layout: flex, `flex-wrap: wrap`, `align-items: center`, `justify-content: space-between`, `row-gap: space.8`, `column-gap: space.32`. Below 720px the nav takes the full width on its own row (`flex-basis: 100%`).
- Wordmark: `type.subheading` (Literata 600), colour `text.primary`, no underline at rest, `translate="no"`, non-breaking space between the words. It is a link, but not a heading, so the page's `h1` stays the page's own title. Hover: underline `link.underline-width` at `link.underline-offset`, colour `text.primary`. Minimum target height `target.primary`, with the text vertically centred (`display: inline-flex; align-items: center; min-block-size: target.primary`).
- Nav list: `<ul>` with `display: flex; flex-wrap: wrap; column-gap: space.24; row-gap: space.4`, no bullets, no padding. Each link `type.interface`, see [navigation link](../components/links-and-buttons.md#navigation-link): colour `text.link`, `min-block-size: target.primary`, inline-flex centred.

### Current page
- The nav link for the current section has `aria-current="page"` and a permanent underline at `link.underline-hover-width`. Other nav links have no underline at rest and get `link.underline-width` on hover.
- "This week" is current on `/`. "Topics" is current on `/topics` and every `/topics/[topic]` page. "How we grade" is current on `/how-we-grade`. On a study page none is current; the topic link above the headline shows where the reader is.
- `aria-current` is `"page"` only on the exact page. On a topic archive, "Topics" gets `aria-current="true"` (the section), with the same visual underline.
- The wordmark never gets `aria-current`.

## Footer

### Content, in order
1. **The disclosure,** in a `<p>`, exactly:

   > Summaries on Nutri Minutes are written by artificial intelligence from each study and checked against it. They are not medical advice.

   This is the wording of PLAN principle 7 and decision 3: "artificial intelligence" in full, "not medical advice", nothing alarming. It is the only place the disclosure appears on the web (no line under headlines).
2. **Footer links,** a `<ul>`:
   - "How summaries are made" → `/how-summaries-are-made` (required by principle 7)
   - "How we grade" → `/how-we-grade`
3. **No-advertising line,** a `<p>`: "No advertising, sponsorship or affiliate links." It states principle 9 where readers look for it, and costs one line.
4. **[Theme control](../components/theme-control.md):** "Theme", System, Light or Dark. Last, because it's a preference rather than information, and because the footer is the calmest place for it: nothing is sticky, and the header stays at three links. Hidden without JavaScript.

The footer is not a `<nav>`: two links don't need a landmark, and it keeps the landmark list short.

### Wireframes

360px:

```
+--------------------------------+  divider
| Summaries on Nutri Minutes are |  type.meta, text.secondary,
| written by artificial          |  max measure.caption
| intelligence from each study   |
| and checked against it. They   |
| are not medical advice.        |
|                                |  space.16
| How summaries are made         |  links stacked, gap space.4,
| How we grade                   |  each min target.min tall
|                                |  space.16
| No advertising, sponsorship or |
| affiliate links.               |
|                                |  space.24
| Theme                          |  legend, space.8
| +--------+ +-------+ +------+  |  theme control, options
| | System | | Light | | Dark |  |  target.primary tall
| +--------+ +-------+ +------+  |
+--------------------------------+
```

1280px (from 720px): two columns, disclosure, no-advertising line and theme control left, links right.

```
+--------------------------------------------------------------------------+
| Summaries on Nutri Minutes are written by        How summaries are made  |
| artificial intelligence from each study and      How we grade            |
| checked against it. They are not medical advice.                         |
| No advertising, sponsorship or affiliate links.                          |
|                                                                          |
| Theme                                                                    |
| +--------+ +-------+ +------+                                            |
| | System | | Light | | Dark |                                            |
| +--------+ +-------+ +------+                                            |
+--------------------------------------------------------------------------+
```

### Tokens
- Top border `border.divider-width` solid `border.divider`, full viewport width like the header's.
- `padding-block: space.40 space.56`.
- All footer text `type.meta`, colour `text.secondary`. The disclosure and the no-advertising line `max-inline-size: measure.caption`.
- Links: [text links](../components/links-and-buttons.md#text-link) (`text.link`, always underlined), `type.meta`. Each link `min-block-size: target.min` with `display: inline-flex; align-items: center`, stacked with `gap: space.4` (targets at least 24px tall and never overlapping).
- From 720px: grid `grid-template-columns: minmax(0, 1fr) auto`, `column-gap: space.56`; the links sit in the second column, top-aligned, stacked. Below 720px everything stacks with `gap: space.16`; from 720px the rows of the first column keep `row-gap: space.16`.
- Theme control: `grid-column: 1` from 720px, after the no-advertising line. `margin-block-start: space.8`, which adds to the `space.16` gap for 24px at every width. Its space is reserved before it is shown, so it never shifts the footer. Its tokens and states are in [its spec](../components/theme-control.md#tokens-and-states).

## Focus

- Every interactive element shows a ring on `:focus-visible`: `outline: focus.ring-width focus.ring-style focus.ring; outline-offset: focus.ring-offset`. Set it once in the global stylesheet for `a`, `button`, `summary`, `input`, `select`, `textarea` and `[tabindex]:not([tabindex="-1"])`.
- Never `outline: none` on an interactive element without this replacement. The only `outline: none` allowed is on non-interactive focus targets: `main` (skip link target) and page `h1`s (route-change target).
- The ring sits in the offset gap on `surface.page` or `surface.raised`; both pairs are recorded in the tokens (`focus.ring` 5.62 and 6.18 light, 8.57 and 7.45 dark). Nothing is drawn on other surfaces, so no other pair is needed. The primary button's ring is outside its Spruce fill, on the page.
- Nothing is sticky or overlaid, so a focused element can't be hidden (WCAG 2.4.11). Headings and in-page targets have `scroll-margin-block-start: space.24` so a jump doesn't land the target on the very edge.
- **Focus order** follows the DOM, which follows the visual order. No positive `tabindex`. No CSS `order` or grid placement that changes the reading order.
- **Route changes:** after a client-side navigation to a new page, move focus to the new page's `h1` (`tabindex="-1"`, no ring). This tells keyboard and screen-reader users where they are and puts the next Tab at the start of the content. Don't move focus for hash links on the same page, or when the back and forward buttons restore a scroll position. Next.js's route announcer also announces the new title; that double announcement is acceptable.
- **Forced colours (Windows contrast themes):** the ring uses `outline`, which survives forced colours. Components that draw marks with backgrounds say how they adapt (grade marks, the interval).

## Light and dark

- Follows the system setting (`prefers-color-scheme`) by default. Readers can override it with the [theme control](../components/theme-control.md) in the footer, which sets `data-theme="light"` or `data-theme="dark"` on `<html>` and stores the choice on this device only.
- Every colour comes from the colour roles; the dark values apply under `@media (prefers-color-scheme: dark)` unless `data-theme="light"` is set, and always under `data-theme="dark"` ([mapping](../components/theme-control.md#how-data-theme-maps-onto-the-tokens)). Components never test the scheme or the theme themselves.
- The shell uses only `surface.page`, `text.primary`, `text.secondary`, `text.link`, `border.divider` and `focus.ring`, plus `border.control`, `border.control-hover`, `button.primary.bg` and `button.primary.text` in the theme control, all with recorded pairs in both themes.
- Screenshots at 360px and 1280px, light and dark, for every page in this folder (ADR 0004). Light and dark by emulated scheme cover the overrides too, since they use the same roles.

## Motion
- The shell has no animation. Link underlines change thickness on hover with no transition (thickness is not a compositor property; the change is instant and small).
- Global rule: under `@media (prefers-reduced-motion: reduce)`, no `motion.*` transition or animation runs. Write motion inside `@media (prefers-reduced-motion: no-preference)` rather than undoing it afterwards.
- `scroll-behavior: smooth` is not used.

## Visually hidden text
The one utility with fixed values, because it is a standard technique rather than a design value:

```css
.visually-hidden:not(:focus):not(:active) {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
```

For inputs that are drawn by their label and must stay hidden even when focused (the [theme control](../components/theme-control.md) radios), use `.visually-hidden-always`: the same declarations without the `:not(:focus):not(:active)` exemption, which exists only for the skip link.

Use it for screen-reader-only text such as "Evidence grade: " before a grade. Never use `display: none` or `aria-hidden` on text that should be read.

## Prose page template
For "How we grade" and "How summaries are made", and later pages such as privacy.

- `h1` in `type.headline-phone` below 720px, `type.headline-desktop` from 720px, `text-wrap: balance`, colour `text.primary`, `margin-block-end: space.24`.
- Body in `type.body`, `max-inline-size: measure.body`. `h2` in `type.section-heading` with `margin-block: space.56 space.16`; `h3` in `type.subheading` with `margin-block: space.40 space.8`. Paragraph spacing `space.16`. Lists with their bullets or numbers kept, `padding-inline-start: space.24`.
- Links inside prose are [text links](../components/links-and-buttons.md#text-link).
- Data: page title, body (structured blocks or Markdown rendered without raw HTML), last updated date. The content of both pages will be drafted for the owner to approve.

## Shared page states

### Loading
Pages are server-rendered and cached, so most visits never see this. When a segment streams (`loading.tsx`):
- The header and footer render at once; only `main` waits.
- `main` shows one line of text, `type.interface`, colour `text.secondary`: "Loading…" plus what is loading where the page says ("Loading this week's findings…"). In a `<p role="status">` so screen readers hear it once.
- No skeletons, shimmer or spinners: they are motion without meaning, and the content arrives quickly.
- Show it only after a short wait if the framework allows, so fast loads don't flash it.

### Page not found (404)
For unknown URLs, unknown study IDs, unknown topics and page numbers past the end. Must return HTTP 404 (`not-found.tsx` / `notFound()`). Call `notFound()` before any Suspense or `loading.tsx` boundary streams: once streaming starts, the status is already 200. So look up the ID or slug in the page (or `generateMetadata`) above the boundary, not inside a streamed child.

```
+--------------------------------+
| (header)                       |
+--------------------------------+
| Page not found                 |  h1
|                                |
| There's no page at this        |  type.body, measure.body
| address. The link may be       |
| wrong, or the page may have    |
| moved.                         |
|                                |
| - This week's findings         |  text links, list
| - Browse topics                |
+--------------------------------+
| (footer with disclosure)       |
+--------------------------------+
```

- Title: "Page not found – Nutri Minutes". `h1` "Page not found", same type as the prose page.
- Body: "There's no page at this address. The link may be wrong, or the page may have moved."
- A `<ul>` of two [text links](../components/links-and-buttons.md#text-link) in `type.interface`, `gap: space.8`: "This week's findings" (`/`) and "Browse topics" (`/topics`).
- No search box (there's no search yet), no illustration, no joke.

### Error (the page couldn't load)
For API failures, timeouts and invalid summaries (`error.tsx` on each segment, `global-error.tsx` for the root layout). Returns HTTP 500 for server errors (the framework's default), or 503 if the API is unreachable and the engineer can set it.

- Title: "This page didn't load – Nutri Minutes". `h1` "This page didn't load".
- Body: "Something went wrong on our side while loading this page. Try again, or come back in a few minutes."
- A [primary button](../components/links-and-buttons.md#primary-button) "Try again" that calls the error boundary's `reset()`, followed by a text link "Go to this week's findings" (`/`), on one row from 720px (`gap: space.24`, `align-items: center`), stacked below 720px with `gap: space.16`.
- If the framework gives an error digest, show it on its own line, `type.meta`, `text.secondary`: "Reference: {digest}" with the digest in `type.figures`, so a reader can quote it. Nothing else about the error is shown: no stack, no API host, no status codes.
- When the error page replaces content after a client-side action, move focus to its `h1`, like a route change.
- `global-error.tsx` replaces the root layout, so it must render its own `<html lang="en-AU">`, the same stylesheet, a minimal header (wordmark only) and the full footer with the disclosure.
- Prefer stale content to this page: cached pages keep serving if the API is down (ADR 0003), so this page should be rare.

### Invalid content
A summary missing its grade, design category, or DOI or PMID is not shown (see [conventions](README.md#content-rules-the-app-enforces)). On a study page that means the error page above, not a partial summary.

## Data
The shell itself needs no API data. The nav and footer links are fixed. If topic names later appear in the header, they come from the same topic list as [Topics](topics.md#data).

## Checks for the engineer
- Tab from the address bar: the first stop is the skip link, visible, with the ring; Enter moves focus into main.
- axe passes on the shell alone, light and dark.
- At 320px wide and at 200% text size, the nav wraps and nothing scrolls sideways.
- In a Windows contrast theme (or Chrome's forced colours emulation), the ring, the wordmark and the divider are visible.
- The footer disclosure text matches this spec exactly, with "artificial intelligence" in full. A unit test on the footer component asserting the exact string is worth having.
