# ADR 0004: Styling and testing for the web app

- **Status:** Accepted
- **Date:** 2026-11-08

## Context
The web app in `web/` is a Next.js App Router app (ADR 0001, ADR 0003). The design system in `design/` defines the visual language as design tokens in the W3C Design Tokens (DTCG) format, with light and dark colour roles and a contrast check (`design/tokens/`). The design is small and custom: one reading column, a few components, and one data graphic, the effect-size interval.

`CLAUDE.md` requires an ADR for the stack and owner agreement for new dependencies. The web app needs a styling approach and a test setup before its first code lands.

## Decision
- **Styling: CSS Modules plus CSS custom properties generated from the tokens.**
  - A build step in `web/` turns `design/tokens/` into one stylesheet of CSS custom properties. Light values sit on `:root` and dark values apply under `prefers-color-scheme: dark`. Aliases become `var()` references.
  - The generated file is not edited by hand. A CI check fails if it is out of date with the tokens.
  - Components use [CSS Modules](https://nextjs.org/docs/app/getting-started/css), which Next.js supports with no extra dependency, plus one global stylesheet for resets, base type and the token variables.
  - Components never use raw colours, sizes or font values, only the token variables.
  - Fonts are self-hosted through `next/font`. The `font.family.*` tokens map to the CSS variables that `next/font` generates.
- **Testing:**
  - **[Vitest](https://vitest.dev/)** for logic and components, with Testing Library for component behaviour.
  - **[Playwright](https://playwright.dev/)** for key flows, plus screenshots at 360px and 1280px wide in light and dark.
  - **[axe-core](https://github.com/dequelabs/axe-core)** through `@axe-core/playwright`, run on every page in the Playwright suite. Any WCAG 2.2 A or AA violation fails CI.
- **CI:** a `web` workflow runs on changes to `web/**` and `design/tokens/**`. It runs lint, type check, unit tests, the token freshness check, a production build, the client-bundle secret check required by ADR 0003, and the Playwright and axe suite.
- **Dependencies:** pinned to exact versions and added in the PR that first uses them, with `npm audit` in CI. Dependabot watches `/web` like `/api`.

## Consequences
- **No styling framework to learn or upgrade:** styles are plain CSS scoped per component, and the tokens stay the single source of truth for every value.
- **Mobile apps reuse the tokens,** not the CSS. The DTCG files stay the shared source.
- **More CSS written by hand** than with a utility framework. Small components and shared token variables keep it manageable.
- **Browser tests need browsers in CI,** which makes the web job slower than the API job. Playwright's own install step provides them.
- **Performance budgets** for Core Web Vitals are still intended, as `.claude/agents/web-engineer.md` says. The tool for them is chosen when they are added.

## Alternatives considered
- **Tailwind CSS:** quick to write and widely used. It can read CSS variables, but it adds a second vocabulary over the tokens and a build dependency, and long class lists make accessibility review of markup harder. Our design is too small to gain much from it.
- **CSS-in-JS (for example styled-components or Emotion):** runtime styling works poorly with React Server Components and adds client JavaScript.
- **Zero-runtime CSS-in-JS (for example vanilla-extract or Panda CSS):** typed styles, but another build tool and dependency for little gain over CSS Modules with typed token names.
- **Jest instead of Vitest:** mature, but slower and needs more configuration for ESM and TypeScript. The API already uses Vitest.
- **Cypress instead of Playwright:** good developer tools, but weaker multi-browser support. Playwright also takes the screenshots we need at set widths and colour schemes.
