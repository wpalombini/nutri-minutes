# Web app

The Nutri Minutes website: Next.js (App Router) on Vercel. It reads data only through our API, from the server ([ADR 0003](../docs/adr/0003-database-api-for-the-web-app.md)). Styling and test tools follow [ADR 0004](../docs/adr/0004-web-app-styling-and-testing.md). Commands are listed in the repo's `CLAUDE.md`.

## Layout

- `src/app/`: routes, the root layout, metadata files (`robots.ts`, `sitemap.ts`, `manifest.ts`), icons and fonts.
- `src/components/`: components, each with its CSS Module.
- `src/lib/api.ts`: the only module that calls the API. It is server-only.
- `src/styles/tokens.css` and `src/generated/theme.ts`: generated from `design/tokens/` by `npm run tokens`. Don't edit them by hand.
- `scripts/`: the token converter and the client bundle secret check.
- `test/`: Vitest unit and component tests. `e2e/`: Playwright and axe tests, which run against a production build and save screenshots to `e2e-screenshots/`.

## Settings

Plain environment variables, set in the Vercel project, or in `web/.env.local` for local runs. None has a `NEXT_PUBLIC_` prefix, so none reaches the browser. `.env.example` at the repo root describes each one.

| Variable                                         | Needed                 | What it is                                                                                                            |
| ------------------------------------------------ | ---------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `API_BASE_URL`                                   | Once a page reads data | The API's origin, such as `https://api.nutriminutes.com`                                                              |
| `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET` | Once a page reads data | The web app's Cloudflare Access service token. The secret is secret.                                                  |
| `SITE_URL`                                       | No                     | The canonical origin. Defaults to `https://nutriminutes.com`.                                                         |
| `SITE_ALLOW_INDEXING`                            | No                     | `true` lets search engines index the site. Anything else keeps every page `noindex` and `robots.txt` disallowing all. |

Pages are static, so these are read at build time: redeploy after changing one.

## Design tokens and fonts

Components use only the CSS variables in `src/styles/tokens.css`: no raw colours, sizes or font values (a unit test checks this). Media queries are the exception, using the breakpoint token values. After a token change, run `npm run tokens` and commit the result; CI fails if it is stale.

Literata and Atkinson Hyperlegible Next come from `next/font/google`, which downloads them at build time and serves them from this site, so browsers never contact Google. The build needs network access to Google Fonts.

## Security headers

`next.config.ts` sets the headers in `src/lib/security-headers.ts` on every response. The Content-Security-Policy is static so pages stay prerendered; it allows inline scripts because Next.js adds them to every App Router page, and the reasons are in that file.
