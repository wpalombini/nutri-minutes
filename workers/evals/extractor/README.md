# Extractor eval dataset

`dataset.jsonl` holds the papers the Extractor eval scores extractions against (ADR 0005), one JSON object per line.

## Fields
- `pmid`, `doi`, `pmcid`, `title`, `publication_types`, `licence`: as in the Evidence Grader dataset (`evals/grader/README.md`). The eval looks papers up by these, never by database ID.
- `grader`: what the Extractor receives from the article's grade, so the eval sends the model what production sends without running the Grader first: `design_category`, `review_includes`, `main_outcome`, `participants`, `duration` and `population`.
- `grader_source`: `production` when `grader` was copied from the article's latest production grade (made with the Grader prompt from #73), `hand` when production didn't grade the paper and the values were written from the abstract.
- `expected`: the correct extraction.
  - The main effect on the main outcome, in the shape `extractions` stores: `measure` (one of the effect measures, or `none`), `estimate`, `ci_lower`, `ci_upper`, `ci_level` and `unit`. Numbers are strings, written exactly as the abstract writes them. A difference stated in words, such as "4.17 days shorter", is negative, with its limits swapped and negated. With `none`, every other effect field is null.
  - `has_absolute`: the abstract gives counts, shares or rates of an outcome for each group compared, so the extraction should include an `absolute` fact.
  - `has_limitation`: the abstract states a limit or a caution about the study's own evidence, so the extraction should include a `limitation` fact.
- `also_accepted`: other main effects that are as defensible as `expected`, such as a co-primary outcome or the same model's other estimate, in the same shape. An alternative with a measure and no numbers accepts any estimate of that measure. Empty when only `expected` is right.
- `label`: `suggested` until the row is reviewed, then `approved`. Only approved rows count towards scores.
- `reviewed_by`: how an approved label was settled: `agreement`, `reconciled`, `owner-rule` or `owner`, as in the Grader dataset.
- `unsure`: true for close calls.
- `note`: why the label was chosen, in a few words.
- `abstract` (optional): stored only for CC BY and CC0 papers, as in the Grader dataset. Every other abstract is fetched from Europe PMC by PMID and cached outside the repo (`evals/abstracts.py`).

## Running it
From `workers/`: `uv run python -m evals.extractor` (options as in `CLAUDE.md`). Each paper goes through production's path: the `grader` fields become the prompt inputs production builds from a grade, and the reply passes the Extractor's checks, asked again up to three times.

Scores:
- **Main effects right:** the measure, estimate, limits and level match `expected` or an `also_accepted` alternative, each number written exactly as labelled ("0.8" isn't "0.80"). "No main effect" is right when a label says so.
- **Main effects found:** the extraction has a main effect exactly when a label does, whatever its numbers.
- **Sign errors:** an estimate that is a label's with the opposite sign.
- **Absolute numbers and stated limits found:** the share of papers with `has_absolute` or `has_limitation` whose extraction has that kind of fact, with counts of such facts on other papers.
- Units are compared ignoring case, spaces and "²" versus "2", and reported only.
- A failed paper counts as wrong everywhere. The summary also gives calls, papers asked again and the cost per paper.

CI (`extractor-eval`) blocks a pull request on any sign error, more than 10 failed papers, main effects right or found falling more than 10 points below `baseline.json`, or stated limits found falling more than 15 points. Absolute numbers are reported only: one of the 5 papers moves the share by 20 points. The baseline also stores a hash of the labels, so any relabel marks it stale.

## Baseline (Haiku 5.5)
After the fixes below, four runs on 2026-11-14 failed 5 to 8 of 56 papers, with main effects right 82–88%, stated limits found 78–89%, no sign errors and US$0.0017–0.0019 per paper (1,000 articles about US$1.80). The baseline is the middle run: 6 failed, 85.7% right. What still fails is mostly the model keeping a number in the population or intervention that isn't in its quote (often a rounded one), or an effect quote it can't place.

Fixes from the first baseline: the model is told which check its last reply failed when asked again; on the last call, extra facts that still fail are left out instead of failing the article; labels and effect quote are ignored when the measure is "none"; an explicit plus sign on a number is accepted; and the prompt says quotes come only from the abstract (the model was copying the Grader's population, even "not stated"), that "95% CI" states the level, and that numbers stay as written, words included.

### First baseline
Two runs on 2026-11-14: most papers fail all three calls (34 and 36 of 56), so main effects right is only 39% and 32%. The baseline is the lower run. Failures, both runs together: 17 replies with no measure but filled effect labels, 17 population quotes not word for word in the abstract, 14 fact numbers or quotes not in the quote or abstract, 9 intervals with limits but no level. One sign error (pmid 42968156, "4.17 days shorter" as +4.17), the known gap from #80. 42–45 papers needed more than one call; US$0.00225 per paper.

## How the papers were chosen
The 56 papers the Grader dataset labels gradable, since the Extractor only reads graded articles. By the Grader dataset's labels they cover every design: 14 reviews, 14 randomised trials, 16 observational studies, 2 non-randomised trials, 5 animal and 5 lab studies. `grader` keeps production's design even where it differs: production graded three of the observational studies (pmids 42968090, 42969229, 42997011) as non-randomised trials.

The 56 papers: 21 with a main effect (8 mean differences, 7 standardised mean differences, 4 odds ratios, 2 hazard ratios) and 35 without one, mostly because the abstract gives only p values, group means or no numbers at all. 13 rows accept another main effect too, 5 papers give absolute numbers per group and 27 state a limit.

## How the labels were settled
Labels were drafted from the abstracts using the Extractor's prompt. A second labeller then labelled every paper blind, from the same rules, without seeing the drafts. They agreed on 49 of 56 papers (`agreement`), including every sign. Of the 7 splits:
- 5 were settled by the written rules (`reconciled`): an interval whose level is never stated is left out; "exploratory" and "preliminary" evidence counts as a stated limit, while a weakness of the measure studied doesn't; and a review with four pooled odds ratios accepts any of them.
- 2 were settled by two rules the repo owner set (`owner-rule`), which the prompt now follows:
  - When the only number is an unadjusted estimate and the link didn't hold after adjustment, there is no main effect. The unadjusted number can still be a result fact.
  - A difference on a score given without a unit takes "points" as its unit.

## Differences stated in words
One row, a time difference stated as "4.17 days" shorter (pmid 42968156), expects -4.17 with limits -6.44 and -1.90: the prompt asks for the negative estimate and says to flip the sign of each limit, so the larger becomes the lower limit. The limits appear in the abstract in the opposite order ("1.90-6.44"), which the Extractor's code check accepts only when the estimate and both limits are negated from words.

Known gap: an interval that crosses zero, stated in words ("1.2 kg less, 95% CI -0.4 to 2.8"), can't pass the check, because the flipped upper limit (0.4) is quoted only with a minus sign. Such articles fail after three calls.
