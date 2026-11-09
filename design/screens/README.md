# Screen specs

What the web app builds, screen by screen. Each spec covers purpose and content hierarchy, layout at 360px and 1280px, tokens, states, keyboard and screen-reader behaviour, motion and the data it needs. They follow the approved [design plan](../PLAN.md) and use the [tokens](../tokens/README.md). Components used on more than one screen are specified once in [`../components/`](../components/README.md).

Build order: the app shell first, because every page sits inside it.

| Spec | Route (suggested) | What it is |
|---|---|---|
| [App shell](app-shell.md) | every page | Skip link, header, main, footer with the disclosure, focus, light and dark, plus the prose page, 404 and error pages |
| [Home](home.md) | `/` | This week's findings: the lead finding with its interval, the other findings as rows, and topics |
| [Study summary](study.md) | `/studies/[id]` | One study: the finding, grade, interval, summary, limits, why this grade, and the study at a glance |
| [Topics](topics.md) | `/topics`, `/topics/[topic]` | The list of topics, and each topic's archive of summaries |

`[id]` is the random public ID planned for articles in [`docs/database.md`](../../docs/database.md#tables-to-come), never the sequential database ID. A readable slug after it is optional; if the app adds one, the ID alone resolves and the page's canonical URL includes the slug.

## Conventions for every spec

### Tokens and units
- Every value is a token, named by its path: `space.24`, `text.secondary`, `type.meta`. In CSS a path becomes a custom property with dots replaced by hyphens (`text.link-visited` becomes `--text-link-visited`), as [`tokens/README.md`](../tokens/README.md#how-apps-consume-the-tokens) describes. Typography roles (`type.*`) become whatever set of variables or classes the token build produces; the spec names the role.
- No raw hex or px values, with the exceptions the tokens README allows: letter spacing in `em` for the two largest headlines, measure in `ch` (`measure.body` is `66ch`), and the `theme-color` hex values.
- Also allowed, because they are not design values: `0`, percentages, `fr`, `auto`, `deg`, `calc()` built from tokens, and the standard visually hidden pattern (see [App shell](app-shell.md#visually-hidden-text)).
- If a spec seems to need a value that has no token, that is a gap in the tokens. Raise it with the designer; don't invent a value in `web/`.

### Breakpoints
Phone first, with only the two token breakpoints:

| Token | Min width | What changes |
|---|---|---|
| (none) | 0 | Phone layout, gutter `layout.gutter` |
| `breakpoint.720` (`layout.breakpoint-gutter`) | 720px | Gutter becomes `layout.gutter-wide`; headlines step up; header goes to one row; home rows go to three columns |
| `breakpoint.960` (`layout.breakpoint-study-grid`) | 960px | Study page: the at-a-glance panel moves beside the summary; home lead headline uses `type.lead-headline` |

"360px" and "1280px" in the specs are the two widths the screenshots are taken at. Everything must also reflow at 320px and at 200% text size with no horizontal scrolling.

### Reader-facing text
- Australian English spelling ("randomised"), sentence case for headings, links and buttons. This overrides the Title Case rule in the web-design-guidelines skill; the design plan's sentence case wins.
- Never "AI": always "artificial intelligence".
- Dates as "7 November 2026" (`Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })`) in a `<time datetime>` element.
- **Study numbers print exactly as the API sends them.** Effect sizes, interval limits, p-values and any other study figure arrive as decimal strings, and the app keeps every digit: "0.80" stays "0.80", "0.0004" stays "0.0004". Don't pass them through `Intl.NumberFormat` with its defaults, which drops trailing zeros and rounds small values to 0. The only changes allowed: replace a leading hyphen-minus with the true minus sign (U+2212), and add thousands grouping to the integer part ("1,250.5"). If you do format with `Intl`, set `minimumFractionDigits` and `maximumFractionDigits` to the string's own number of decimals. Parse the string to a number only to position marks in the drawing.
- **Counts** (people in a study, numbers of summaries) use `Intl.NumberFormat('en-AU')`. Ranges are written with "to" ("0.80 to 1.04"), never a hyphen or dash, so a range is never misread as a negative number.
- Loading text ends with an ellipsis character: "Loading…".
- Curly quotes and apostrophes in all copy.
- The brand name "Nutri Minutes" has a non-breaking space between the words and `translate="no"` where it appears as the wordmark.

### Content rules the app enforces
These come from `CLAUDE.md` and the plan, and the app fails closed on them rather than trusting the API:
- **Every summary shows its evidence grade and its source.** The source is the DOI, or the PubMed record when there is no DOI. A summary that arrives without a grade level, a study design category or either source identifier is invalid. Lists leave it out; the study page shows the error page. Either way, log it with the summary's public ID.
- **Observational, animal and lab studies are always labelled** with the [study design label](../components/study-design-label.md), wherever the summary appears.
- **Nothing relies on colour alone.** Every state has text, and every mark has a text equivalent.
- **The disclosure is in the footer of every page,** including the 404 and error pages.

### Accessibility floor
WCAG 2.2 AA, as in `.claude/agents/designer.md`. The specs say how each screen meets it; the axe suite in ADR 0004 is a floor, not the whole check.
