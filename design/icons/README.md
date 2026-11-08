# Site icon

The icon is a small version of the plan's one bold element, the interval (see [PLAN.md](../PLAN.md), section 6): a Beetroot interval bar with the point-estimate diamond in the middle, filled with the page colour and outlined in Spruce ink. On a log scale an interval is symmetric around its estimate, so the diamond sits in the centre. There is no text, because letters don't survive at 16px.

It's original work owned by the project (see [ASSETS.md](../ASSETS.md)).

## Files

| File | What it's for |
|---|---|
| `icon.svg` | Master for small sizes: browser tabs, bookmarks, the SVG favicon. Drawn on a 16-unit grid so the bar edges land on whole pixels at 16, 32 and 48. The diamond outline is 2 units thick, because a 1px diagonal line blurs away at 16px. |
| `icon-app.svg` | The same mark for large sizes, with a 1-unit outline that matches the plan's proportions. Rounded tile, transparent corners. Source of `icon-192.png` and `icon-512.png`. |
| `icon-maskable.svg` | Full-bleed square for masks (Android adaptive icons, iOS). The mark fits inside the maskable safe zone. Source of `icon-maskable-512.png` and `apple-touch-icon.png`. |
| `favicon.ico` | 16, 32 and 48px, PNG-compressed entries, from `icon.svg`. For browsers and tools that only ask for `/favicon.ico`. |
| `apple-touch-icon.png` | 180 by 180, opaque (no alpha channel). iOS home screen; iOS rounds the corners itself. |
| `icon-192.png`, `icon-512.png` | Web app manifest icons, `purpose: "any"`. |
| `icon-maskable-512.png` | Web app manifest icon, `purpose: "maskable"`. |
| `export-icons.cjs` | Regenerates every raster file from the SVGs. |

## Light and dark tabs: a solid tile

Every version sits on its own Assay paper tile, so the mark is drawn on the same colour on every tab, light or dark. I chose this over a transparent icon that swaps colours with `prefers-color-scheme` inside the SVG because:

- the `.ico` and `.png` files can't adapt, so a media query would make the SVG and raster versions look different;
- browsers apply the SVG's `prefers-color-scheme` from the system or browser setting, which doesn't always match the tab strip's colour, so a transparent icon can land dark on dark;
- with a tile, the contrast that matters (mark against its own background) is fixed and measured once.

The cost is a light square on dark tabs. It reads clearly there (the tile is 14.22:1 against `#202124`); on light tabs the tile edge almost disappears (1.13:1 against `#FFFFFF`), and the mark stands on its own.

## Colours and contrast

All light-theme values. Ratios are the ones recorded in `tokens/color.light.tokens.json`, recomputed with `tokens/check_contrast.py`'s formula.

| Part | Token | Hex | Against | Ratio (needs 3:1) |
|---|---|---|---|---|
| Tile | `surface.page` (Assay paper) | `#EDF2EF` | — | — |
| Interval bar | `data.interval` (Beetroot) | `#97245A` | tile | 6.83:1 |
| Diamond fill | `data.estimate-fill` (Assay paper) | `#EDF2EF` | bar | 6.83:1 |
| Diamond outline | `data.estimate-outline` (Spruce ink) | `#122B27` | tile | 13.24:1 |

As in the full-size interval, the outline is only 1.94:1 against the bar, so nothing relies on it there: inside the bar the diamond is carried by its fill, and above and below the bar by the outline against the tile.

Tile against typical tab colours, for information: `#FFFFFF` 1.13:1, `#F1F3F4` 1.02:1, `#202124` 14.22:1, `#35363A` 10.66:1. On light tabs the mark itself carries the contrast (bar 7.73:1 and 6.95:1, outline 14.99:1 and 13.47:1).

## Geometry

- `icon.svg`, viewBox `0 0 16 16`: tile 16 by 16 with corner radius 2; bar x 1–15, y 6–10; diamond centred at (8, 8), outer half-diagonal 4.5, outline 2.
- `icon-app.svg`: same, outline 1 (outer half-diagonal still 4.5).
- `icon-maskable.svg`, viewBox `-3 -3 22 22`: the `icon-app.svg` mark on a 22-unit full-bleed square, no corner radius. The farthest points of the mark (the bar corners) are 7.28 units from the centre; the safe zone is a circle of radius 40% of the icon size, 8.8 units, so the whole mark is inside it. Source: [W3C Web Application Manifest, icon masks and safe zone](https://www.w3.org/TR/appmanifest/#icon-masks), checked 8 November 2026.

## Using it in the web app (Next.js App Router)

Copy the files into `web/` like this. Next.js generates the `<link>` tags from the file names ([app icons](https://nextjs.org/docs/app/api-reference/file-conventions/metadata/app-icons) and [manifest](https://nextjs.org/docs/app/api-reference/file-conventions/metadata/manifest) docs, checked 8 November 2026).

| From `design/icons/` | To | Next.js output |
|---|---|---|
| `favicon.ico` | `app/favicon.ico` (top level of `app/` only) | `<link rel="icon" href="/favicon.ico" sizes="any">` |
| `icon.svg` | `app/icon.svg` | `<link rel="icon" href="/icon.svg?…" type="image/svg+xml" sizes="any">` |
| `apple-touch-icon.png` | `app/apple-icon.png` | `<link rel="apple-touch-icon" href="/apple-icon.png?…" type="image/png" sizes="180x180">` |
| `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` | `public/icons/` | referenced from `app/manifest.ts` |

Browsers that support SVG favicons use `icon.svg`; the rest fall back to `favicon.ico`.

`app/manifest.ts` (Next.js serves it at `/manifest.webmanifest` and adds `<link rel="manifest">`):

```ts
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Nutri Minutes",
    short_name: "Nutri Minutes",
    start_url: "/",
    display: "standalone",
    background_color: "#EDF2EF",
    theme_color: "#EDF2EF",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
```

`background_color` and `theme_color` are `surface.page` (light). For the page's own `<meta name="theme-color">`, follow `tokens/README.md`: match the page background in each theme (`#EDF2EF` light, `#0E1C19` dark, using `media="(prefers-color-scheme: dark)"`), via the `viewport` export's `themeColor`.

Keep `maskable` and `any` as separate entries; a single icon with `purpose: "any maskable"` looks too small where it isn't masked.

## Re-exporting

Edit the SVGs by hand (keep them free of editor metadata), then run, from the repo root, with an existing `sharp` install on `NODE_PATH` (Next.js uses `sharp` for image optimisation, so the web app's `node_modules` usually has it):

```sh
NODE_PATH=web/node_modules node design/icons/export-icons.cjs
```

It writes all five raster files next to the SVGs. `sharp` renders SVG with librsvg; the committed files were made with sharp 0.34.5 (librsvg 2.61.2). If the colours change, update the hex values in all three SVGs and in `export-icons.cjs` (the Apple icon's flatten background), then recheck the contrast table above.

Export spec, if you use another tool: `favicon.ico` = `icon.svg` at 16, 32 and 48px; `icon-192.png` and `icon-512.png` = `icon-app.svg`; `icon-maskable-512.png` = `icon-maskable.svg` at 512; `apple-touch-icon.png` = `icon-maskable.svg` at 180, flattened onto `#EDF2EF` with no alpha channel.

## Alternative considered

A solid Spruce ink diamond on the bar, separated from it by a thin paper-coloured gap. It's a little bolder at 16px, but it changes the plan's diamond (hollow, page-filled) into a different symbol, so the delivered icon keeps the plan's diamond.
