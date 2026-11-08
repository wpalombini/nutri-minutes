# Design tokens

The single source for Nutri Minutes colours, type, spacing, borders, motion and layout, shared by the web app now and mobile apps later. The values come from the approved [design plan](../PLAN.md).

Format: [W3C Design Tokens Format Module 2025.10](https://www.designtokens.org/TR/2025.10/format/) (DTCG), with colours as described in its [Color module](https://www.designtokens.org/TR/2025.10/color/). Each token has a `$value`, a `$type` (its own or its group's) and often a `$description`. Aliases point at another token with `{group.token}`.

## Files

| File | What it holds |
|---|---|
| `base.tokens.json` | Raw values: the named palette (each colour with a `light` and a `dark` value), font families, weights, the type scale with line heights and letter spacing, spacing, radii, border widths, durations, easing curves, breakpoints and layout widths. |
| `roles.tokens.json` | Semantic roles that are the same in both themes: type styles (`type.body`, `type.meta`...), measure, layout, target sizes, border widths and styles, link underline, focus ring size, grade mark and interval sizes, and transitions. |
| `color.light.tokens.json` | Colour roles for the light theme. |
| `color.dark.tokens.json` | Colour roles for the dark theme, with exactly the same paths as the light file. |
| `check_contrast.py` | Checks the files (see below). |

A theme is `base` + `roles` + one colour file. No token is defined in more than one file. Apps use roles, never the palette directly.

## Naming

- Lower case, words joined with hyphens, groups separated by dots in aliases: `text.link-visited`, `border.control-hover-width`.
- Roles name what something is for (`surface.raised`, `focus.ring`, `grade.mark`, `data.interval`), not what it looks like.
- Base steps that are sizes are named by their pixel value at the browser default (`space.24`, `font.scale.18`), so they can be matched to the plan at a glance. Font sizes and spacing are stored in `rem` so they follow the reader's font-size setting.
- Two values the DTCG format can't express directly are documented in `$description`: letter spacing in `em` for the two largest headlines (stored as the equivalent `px`), and measure in `ch` (stored as a number).

## Contrast records

Every foreground colour role records the surfaces it may be used on in `$extensions["io.github.wpalombini.nutri-minutes"].contrast`, for example:

```json
{ "on": "{surface.page}", "kind": "text", "min": 4.5, "ratio": 13.24, "use": "primary text" }
```

`kind` is `text` (WCAG 1.4.3, at least 4.5:1, even for large text) or `non-text` (WCAG 1.4.11, at least 3:1: control borders, icons, focus ring, grade marks and chart marks). Only pairs that pass are defined. If a colour isn't recorded against a surface, don't use it there. Surfaces have no records, and `border.divider` is marked `decorative` because it carries no meaning.

## Checking

```sh
python3 -I design/tokens/check_contrast.py
```

Standard library only. It merges each theme, checks that every token has a type and every alias resolves, that each colour's `hex` matches its components, that the light and dark files have the same roles, and that every colour role is a surface, decorative or has contrast records. Then it recomputes every recorded pair (WCAG 2.x relative luminance), checks it against its threshold and checks that the recorded ratio is still right. It exits 1 on any problem. Run it after any token change, and in CI once there is a design check job.

## Fonts and figures

Licences and sources are in [`../ASSETS.md`](../ASSETS.md).

Atkinson Hyperlegible Next has tabular figures. Its OpenType `GSUB` table includes the `tnum` (and `pnum`) features, and its default figures are proportional (digit widths 407 to 648 units). Literata also has `tnum`, plus `lnum` and `onum`. So numbers that are compared or aligned (the at-a-glance panel, tables, axis ticks) use Atkinson with `font-variant-numeric: tabular-nums`, as the `type.figures` style records. Checked on 8 November 2026 by reading the feature list of `AtkinsonHyperlegibleNext[wght].ttf` and `Literata[opsz,wght].ttf` from the [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl).

## How apps consume the tokens

- **Web app (Next.js):** a later build step, written in the web app, turns these files into CSS custom properties. Each path becomes a variable (`text.link-visited` becomes `--text-link-visited`). Base and role tokens go on `:root`. Light colours go on `:root` too, and dark colours under `@media (prefers-color-scheme: dark)`, plus a `data-theme` override if a theme switch is added. The page also sets `color-scheme` and a matching `theme-color`. Aliases are emitted as `var()` references, so the role layer stays visible in the CSS. Typography tokens become a set of variables or utility classes, and the `$extensions` values for `type.figures` become `font-variant-numeric: tabular-nums`. Under `prefers-reduced-motion: reduce`, the `motion.*` transitions are not applied.
- **Mobile apps (later):** the same files are converted to platform values: `rem` × 16 to points (iOS) or `sp` for type and `dp` for everything else (Android), and the light and dark colour files to the platform's light and dark appearance. The contrast records apply unchanged.
- The two colour files follow the DTCG Resolver module's idea of one shared set plus a light or dark modifier. A [resolver document](https://www.designtokens.org/TR/2025.10/resolver/) can be added later if a tool needs one.

Don't edit token values in app code. Change them here, run the check, and regenerate.
