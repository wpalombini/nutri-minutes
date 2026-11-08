# Nutri Minutes design plan

Status: draft for the repo owner's approval. Nothing in the design system, tokens or screen specs is built until this is approved. Once it is, the tokens go into `design/tokens/` (DTCG JSON) and the screens into `design/screens/`.

## 1. Subject, audience and primary job

- **Subject:** new nutrition research, graded for how much it can be trusted. The materials of this world are effect sizes, confidence intervals, study designs, sample sizes, DOIs and the limits of what a study can claim. The visual identity comes from those, not from food photography or wellness imagery.
- **Audience, served equally:**
  - Science enthusiasts: younger, computer literate, want the numbers and expect a polished, modern product.
  - Adults 50+ who want to stay strong and independent: need comfortable reading, large targets and simple navigation.
- **Primary job:** let a reader understand in under a minute what a new study found, how sure we can be, and what it does not show, then follow the source.
- **Pages in scope (MVP):** home (this week's findings), study summary, archive by topic. Later: episode pages with an audio player, and email sign-up.

## 2. Palette

Six named base values. One accent, Beetroot, is reserved for links and the effect-size interval, so wherever it appears it means "a number from the study" or "go somewhere".

| Name | Light | Dark | Role |
|---|---|---|---|
| Assay paper | `#EDF2EF` | `#0E1C19` | Page surface: a cool, slightly green paper, not cream and not white |
| Bright paper | `#FAFCFB` | `#162925` | Raised surface (study-at-a-glance panel, inputs) |
| Spruce ink | `#122B27` | `#E3EDE9` | Primary text, evidence-grade marks, button fill |
| Lichen | `#4A5F59` | `#A2B6AF` | Secondary text, chart axes, the no-difference line, control borders |
| Beetroot | `#97245A` | `#F28DB8` | Links and the effect-size interval |
| Cobalt | `#1F5FAD` | `#8DB8F2` | Focus ring only |

Decorative dividers are Lichen at 30% opacity. They carry no meaning, so they have no contrast requirement; anything a reader needs to see (control borders, chart axes) uses full Lichen.

### Semantic roles (become tokens)

| Role | Value |
|---|---|
| `surface.page` | Assay paper |
| `surface.raised` | Bright paper |
| `text.primary` | Spruce ink |
| `text.secondary` | Lichen |
| `text.link` | Beetroot |
| `data.interval` | Beetroot |
| `data.axis`, `data.null` | Lichen |
| `border.control` | Lichen |
| `border.divider` | Lichen 30% (decorative) |
| `focus.ring` | Cobalt, 3px, 3px offset (the offset gap is always the page or raised surface) |
| `grade.mark` | Spruce ink, for every grade level |
| `button.primary.bg` / `button.primary.text` | Spruce ink / Assay paper |

Grades deliberately share one colour. No green, amber or red grade scale: see section 5.

### Contrast (computed, WCAG 2.x relative luminance)

Computed with the script in the appendix, not estimated.

| Pair | Needs | Light | Dark |
|---|---|---|---|
| Spruce ink on Assay paper (primary text) | 4.5 | 13.24 | 14.64 |
| Spruce ink on Bright paper | 4.5 | 14.55 | 12.74 |
| Lichen on Assay paper (secondary text) | 4.5 | 6.04 | 8.21 |
| Lichen on Bright paper | 4.5 | 6.63 | 7.15 |
| Beetroot on Assay paper (link, interval) | 4.5 | 6.83 | 7.74 |
| Beetroot on Bright paper | 4.5 | 7.50 | 6.73 |
| Assay paper on Spruce ink (button label) | 4.5 | 13.24 | 14.64 |
| Lichen on Assay paper (control border, axis) | 3 | 6.04 | 8.21 |
| Lichen on Bright paper (control border, axis) | 3 | 6.63 | 7.15 |
| Cobalt on Assay paper (focus ring) | 3 | 5.62 | 8.57 |
| Cobalt on Bright paper (focus ring) | 3 | 6.18 | 7.45 |

Every pair passes AA; every text pair passes 4.5:1 even where it would only need 3:1 as large text. No other text and surface pairs are defined.

## 3. Typefaces

Both are SIL Open Font License, on Google Fonts for previewing, and will be self-hosted in the app.

| Face | Role | Why |
|---|---|---|
| **Literata** (variable, optical size 7–72, weights 400 and 600, italic 400) | Headlines and summary body text | Designed for long-form screen reading. Its optical-size axis lets the same family be sturdy at 18px and refined at 48px. A reading serif fits "plain-English summaries you actually read". |
| **Atkinson Hyperlegible Next** (400, 700) | Interface, navigation, metadata, numbers, chart labels | Designed by the Braille Institute for low-vision legibility: distinct I/l/1 and O/0, which matters when numbers are the content. Modern enough for the enthusiast audience. |

The two are clearly distinct (reading serif and a humanist, legibility-first sans), so the split itself tells readers what they're looking at: Literata is the story, Atkinson is the data and the controls.

To verify before tokens are written: whether Atkinson Hyperlegible Next has tabular figures (`tnum`). If it doesn't, figures in tables and the at-a-glance panel use Literata's tabular lining figures instead.

### Type scale

Adapted from Bringhurst's classical scale, with 30 added between 24 and 36: 16, 18, 21, 24, 30, 36, 48, 60. Nothing is set below 16px.

| Size / line height | Face and weight | Use |
|---|---|---|
| 60 / 1.05 | Literata 600, −0.015em | Home lead headline, desktop only |
| 48 / 1.1 | Literata 600, −0.01em | Page headline, desktop |
| 36 / 1.15 | Literata 600 | Page headline, phone |
| 30 / 1.2 | Literata 600 | Section heading |
| 24 / 1.25 | Literata 600 | Subheading inside a summary |
| 21 / 1.3 | Literata 600 | Finding titles in lists |
| 18 / 1.7 | Literata 400 | Summary body (serif gets the extra leading) |
| 18 / 1.6 | Atkinson 400 / 700 | Interface text, figure captions |
| 16 / 1.5 | Atkinson 400 / 700 | Metadata, axis labels, the footer disclosure |

Headlines are sentence case and say the finding itself ("More dairy linked to slightly fewer hip fractures, but the range includes no difference"), with `text-wrap: balance`. That is how type is an active part of the design here: the headline does the job a hero image would do elsewhere, and its honesty is the brand.

Measure: summary body max 66ch; captions and notes max 62ch.

## 4. Layout concept

One sentence: a single left-aligned reading column, with the study's numbers drawn to scale above the prose and a quiet "study at a glance" panel beside it on wide screens.

- Left-aligned throughout. Nothing centred except where a control demands it.
- Max content width 1120px; side gutter 16px on phones, 32px from 720px.
- Study page desktop grid: reading column up to 680px, a 300px at-a-glance column, 56px gap. Below 960px the panel follows the summary.
- Rows, not cards. Lists of findings are full-width rows separated by decorative dividers. The only filled panel on any page is "study at a glance", so the one raised surface means "the facts of this study".
- Structure carries meaning: a solid outline means a control; a dashed outline means "absence or limits" (what the study does not show) and, in the preview only, "sample content".
- No sticky headers or sidebars, so nothing can cover a focused element.

### Home, phone (360px)

```
+--------------------------------+
| Nutri Minutes                  |
| This week  Topics  How we grade|
+--------------------------------+
| This week's findings,          |
| published 7 Nov 2026           |
|                                |
| Falls and independence (link)  |
| Twice-weekly balance           |
| classes cut falls in adults    |
| over 70                        |  <- Literata 36
| [###.] Moderate certainty 3/4  |
| (Randomised trial)             |
|          No difference         |
|  ------<====◆====>-|---------  |  <- the interval, full width
|  0.5   0.67      1   1.5    2  |
|  Fewer falls        More falls |
| Falls were 23% less frequent   |
| (RR 0.77, 95% CI 0.64-0.93)... |
|--------------------------------|
| More dairy linked to slightly  |
| fewer hip fractures, but...    |
| Bone health                    |
| --<=◆=|>---   [##..] Low       |
|--------------------------------|
| Protein at breakfast and leg   |
| strength in mice...            |
| (Animal study) [#...] Very low |
|--------------------------------|
| Browse by topic                |
| [Bone health] [Muscle and      |
| strength with age] [Falls...]  |
+--------------------------------+
| Footer disclosure, wording in  |
| principle 7. How summaries are |
| made (link)                    |
+--------------------------------+
```

### Home, desktop (1280px)

```
+--------------------------------------------------------------------------+
| Nutri Minutes                          This week   Topics   How we grade |
+--------------------------------------------------------------------------+
| This week's findings, published 7 November 2026                          |
| Falls and independence                                                   |
| Twice-weekly balance classes cut                                         |
| falls in adults over 70                         <- Literata 48-60, 22ch  |
| [###.] Moderate certainty 3 of 4   (Randomised trial)                    |
|                               No difference                              |
|  0.5 ------------<=========◆=========>------|------------------------ 2  |
|  Fewer falls                                                 More falls  |
|  Falls were 23% less frequent (rate ratio 0.77, 95% CI 0.64 to 0.93)...  |
|--------------------------------------------------------------------------|
| More dairy linked to slightly fewer hip... | --<=◆=|>-- | [##..] Low     |
| Bone health                                |            |                |
|--------------------------------------------------------------------------|
| Protein at breakfast and leg strength...   | (Animal)   | [#...] Very low|
|--------------------------------------------------------------------------|
| Browse by topic                                                          |
| [Bone health] [Muscle and strength with age] [Falls and independence]    |
| [Heart and metabolism] [Brain health] [Longevity] [Genes and diet]       |
+--------------------------------------------------------------------------+
| Footer disclosure (principle 7)                How summaries are made    |
+--------------------------------------------------------------------------+
```

Wireframe rows are shortened to fit. The real rows always show full labels, such as "(Animal study)" and "Very low certainty".

### Study page, phone (360px)

```
+--------------------------------+
| Nutri Minutes   (nav)          |
+--------------------------------+
| Bone health (link)             |
| More dairy linked to slightly  |
| fewer hip fractures, but the   |
| range includes no difference   |  <- h1, Literata 36
| [##..] Low certainty 2 of 4    |
| (Observational study)          |
|          No difference         |
|  -------<===◆==|=>-----------  |
|  0.5   0.67      1   1.5    2  |
|  Lower risk        Higher risk |
| Hip fracture risk was 9% lower |
| (HR 0.91, 95% CI 0.80-1.04).   |
| The range crosses 1, so no     |
| difference is still plausible. |
|                                |
| What the study found           |
| (Literata 18/1.7 body)         |
| In plain numbers: 19 vs 21 in  |
| every 1,000 over 11 years.     |
| +- - - - - - - - - - - - - - -+|
| | What this study does not    ||  <- dashed = limits
| | show                        ||
| | - not cause and effect ...  ||
| +- - - - - - - - - - - - - - -+|
| > Why this grade is low        |  <- expandable section, 44px target
|   certainty                    |
| +----------------------------+ |
| | Study at a glance          | |  <- the one raised panel
| | Design / People / Followed | |
| | for / Main result /        | |
| | Funding / Source DOI /     | |
| | Licence                    | |
| +----------------------------+ |
+--------------------------------+
| Footer disclosure, wording in  |
| principle 7. How summaries are |
| made (link)                    |
+--------------------------------+
```

### Study page, desktop (1280px)

```
+--------------------------------------------------------------------------+
| Nutri Minutes                          This week   Topics   How we grade |
+--------------------------------------------------------------------------+
| Bone health                                                              |
| More dairy linked to slightly fewer hip fractures,                       |
| but the range includes no difference                <- h1, Literata 48   |
| [##..] Low certainty 2 of 4   (Observational study)                      |
|                               No difference                              |
|  0.5 ------------------<=====◆=====|==>------------------------------ 2  |
|  Lower risk                                                Higher risk   |
|  Hip fracture risk was 9% lower (HR 0.91, 95% CI 0.80 to 1.04). ...      |
|                                                                          |
| What the study found                          | +----------------------+ |
| Researchers followed 31,200 adults ...        | | Study at a glance    | |
| (66ch measure)                                | | Design               | |
|                                               | | People               | |
| +- - - - - - - - - - - - - - - - - - - - - -+ | | Followed for         | |
| | What this study does not show             | | | Main result          | |
| +- - - - - - - - - - - - - - - - - - - - - -+ | | Funding              | |
|                                               | | Source (DOI link)    | |
| > Why this grade is low certainty             | | Licence              | |
|   + Raises confidence  - Lowers confidence    | +----------------------+ |
+--------------------------------------------------------------------------+
| Footer disclosure (principle 7)                How summaries are made    |
+--------------------------------------------------------------------------+
```

States to specify in the screen specs later: no confidence interval reported (show the numbers in words and the sentence "The abstract doesn't report a range", never a drawn interval with an invented range); outcome on a linear scale (mean difference with units, no-difference line at 0); empty week; loading; API error.

## 5. How the evidence grade is shown without relying on colour

Each grade is shown by three things at once, none of which is colour:

1. **Shape:** four squares, filled for each level reached, outlined for the rest (`[##..]` = 2 of 4). All in Spruce ink, so the marks read the same in greyscale, print and every kind of colour vision.
2. **Words:** the level name is always visible next to the marks: "High", "Moderate", "Low" or "Very low certainty", plus "2 of 4" on study pages.
3. **Accessible name:** the marks are `aria-hidden`; the text carries the meaning for screen readers ("Low certainty, 2 of 4").

The study design is a separate, always-visible text label in parentheses, with no outline (outlines mean controls): "Randomised trial", "Observational study", "Animal study", "Lab study", "Review of studies". This meets the rule that observational and animal studies are labelled as such, independent of the grade.

"Why this grade" lists reasons in two groups, "Raises confidence" (plus icon) and "Lowers confidence" (minus icon), each with a text heading, drawn from design, size, duration, population, and funding and conflicts.

## 6. The one bold element: the interval

The effect size, drawn to scale, near the top of every study page and on the lead finding on the home page: a wide horizontal axis, a labelled "No difference" line, the confidence interval as a thick Beetroot bar and the point estimate as a diamond filled with the page colour and outlined in Spruce ink. The fill carries the contrast against the bar (page colour on Beetroot is 6.83:1 light and 7.74:1 dark); the outline is only about 1.9:1 against Beetroot, so nothing may rely on it. Words at each end ("Lower risk" / "Higher risk", "Fewer falls" / "More falls") say which way is good, so no one has to decode a ratio. A plain-English caption under it always repeats the numbers in full (estimate, 95% CI, and an absolute version where the study gives one).

It's the bold element because it is the most characteristic object in this subject (it's the core of a forest plot) and it is honest by construction: an interval that crosses the no-difference line looks like it. It's the visual answer to hype. Ratios use a log scale, so 0.5 and 2 sit equally far from 1.

Everything around it stays quiet: one accent colour used nowhere else except links, no imagery, no gradients, no shadows. Lists use a small 120px version of the same interval as a glyph.

## 7. Motion principles

- **One orchestrated moment:** on a study page, the interval grows outward from the point estimate once on load (about 500ms, ease-out). It shows that the range spreads around an estimate. No other entrance animations, no scroll-triggered reveals.
- **Motion answers actions:** opening "Why this grade" expands in place; the audio player (later) shows progress. Hover changes link underline thickness and control border weight, not position.
- Animate `transform` and `opacity` only; never `transition: all`.
- `prefers-reduced-motion: reduce` removes the interval growth and all non-essential transitions. Nothing needs motion to be understood.
- No autoplaying audio or looping animation.

## 8. Principles

1. **The finding is the headline.** Headlines state the result in plain words, including its limits. No teaser headlines.
2. **Show the range, not just the number.** Every effect size appears with its interval, the direction in words and, where available, absolute numbers.
3. **Limits are first-class content.** "What this study does not show" gets its own marked block, never a footnote.
4. **Meaning never rides on colour alone.** Grades, study types and states always have text and shape.
5. **One accent, one meaning.** Beetroot means a study number or a link. Nothing decorative uses it.
6. **Comfortable by default.** 18px reading text, 16px minimum, 44px primary targets, reflow at 320px, 200% zoom without loss.
7. **Calm disclosure.** The footer of every page says the summaries are written by artificial intelligence from each study and checked against it, that they are not medical advice, and links to "How summaries are made". It's secondary text at 16px, visible but not alarming. Reader-facing text spells out "artificial intelligence" and never uses "AI".
8. **The source is one tap away.** Every summary shows the DOI as a link in the at-a-glance panel.
9. **Nothing to sell.** No ads, affiliate links, sponsored slots, pop-ups or dark patterns. Email sign-up (later) is one labelled field and one button.

## 9. Review against the brief

What a generic first pass for "health science newsletter site" tends to produce, what this plan avoids and what was revised:

**Defaults avoided**
- Cream background with a serif display and a terracotta accent: the page is a cool green-grey paper with a beetroot accent instead.
- Clinical white, teal and a geometric sans (the stock "health tech" look): no teal, no white page.
- Traffic-light grades (green, amber, red): colour-reliant and implies "good" and "bad" studies; replaced by monochrome marks plus words.
- SaaS card grid with identical rounded cards and soft shadows: findings are rows; there's one raised panel with one meaning.
- Broadsheet layout with hairline rules and dense columns: one reading column, generous space, dividers kept faint and decorative.
- Template chrome: no all-caps eyebrows, no labels joined with middle dots, no "WORD — fragment" labels, no monospace data labels, no arrows appended to links, no 01/02/03 markers (none of this content is a sequence).
- Food photography and wellness imagery: none; the data is the image.

**Revisions made after reviewing the first draft**
- **Hero:** the first draft opened the home page with a big percentage and a small label ("18% lower risk"). That's the default stat treatment, and a relative risk on its own is the hype the pipeline is built to stop. Replaced with the interval drawn to scale, the no-difference line and absolute numbers in the caption.
- **Display face:** the first draft considered a high-contrast display serif (Fraunces) for headlines. It pulled towards the generic editorial look and was harder to read at phone sizes for older readers. Replaced with Literata at a high optical size: one reading family from 18px to 60px.
- **Study facts:** the first draft put the facts in a margin column ruled off with hairlines, which read as broadsheet. Kept the column for desktop but made it the single raised panel, with no rules.
- **Palette check:** the first rule colour (`#7C918A`) failed 3:1 for control borders on the page in light mode (2.96:1). Control borders and chart axes now use Lichen at full strength; the lighter value survives only as a decorative divider.

## 10. Decisions

1. **Grade scale words:** four levels using GRADE's terms: "High", "Moderate", "Low" and "Very low certainty".
2. **Accent:** Beetroot, as above.
3. **Disclosure:** in the footer of every page only, worded with "artificial intelligence" in full (principle 7). No line under the headline.

## Appendix: contrast script

The ratios above came from this script (WCAG 2.x relative luminance; run with `python3`). It will move into `design/` with the tokens once approved, so every ratio in the tokens can be re-checked.

```python
def lum(h):
    h = h.lstrip('#'); c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def ratio(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)

themes = {
    'light': dict(paper='#EDF2EF', raised='#FAFCFB', ink='#122B27', lichen='#4A5F59', beet='#97245A', focus='#1F5FAD'),
    'dark':  dict(paper='#0E1C19', raised='#162925', ink='#E3EDE9', lichen='#A2B6AF', beet='#F28DB8', focus='#8DB8F2'),
}
pairs = [('ink', 'paper', 4.5), ('ink', 'raised', 4.5), ('lichen', 'paper', 4.5), ('lichen', 'raised', 4.5),
         ('beet', 'paper', 4.5), ('beet', 'raised', 4.5), ('paper', 'ink', 4.5),
         ('focus', 'paper', 3.0), ('focus', 'raised', 3.0)]
for t, v in themes.items():
    for f, b, need in pairs:
        r = ratio(v[f], v[b]); print(f"{t} {f} on {b}: {r:.2f} (needs {need}) {'pass' if r >= need else 'FAIL'}")
```
