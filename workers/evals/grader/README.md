# Evidence Grader eval dataset

`dataset.jsonl` holds the papers the Evidence Grader eval scores grades against (ADR 0005), one JSON object per line.

## Fields
- `pmid`, `doi`, `pmcid`: the paper's identifiers. Every paper has a PMID. The eval looks papers up by these, never by database ID.
- `title`, `publication_types`, `grant_agencies`: as Scout stored them (grant agencies from Europe PMC's grant list, deduplicated, at most 10), so the eval sends the model what production sends.
- `licence`: the licence code Scout recorded. The rule on abstracts below depends on it.
- `sample`: `stratified` for papers picked at random within design groups, `picked` for hand-picked edge cases.
- `expected`: the correct grade.
  - `gradable`: false for papers the Grader doesn't grade, with the reason in `not_gradable` (`narrative_review`, `case_report`, `protocol` or `not_a_study`) and every other field null.
  - `design_category`: `randomised_trial`, `non_randomised_trial`, `observational`, `review`, `animal` or `lab`.
  - `review_includes` and `review_reported_level`: for reviews only, what the review combines and the certainty it reports for its main outcome (1 to 4), or null.
  - `level`: the grade for the main outcome, 1 very low to 4 high.
- `label`: `suggested` until the row is reviewed, then `approved`. Only approved rows count towards scores.
- `reviewed_by`: how an approved label was settled. `agreement`: the suggested label and an independent blind labelling agreed. `reconciled`: they differed, and the label was settled by the written grading rules. `owner-rule`: a rule the repo owner set for a kind of paper decided it. `owner`: the owner reviewed the paper.
- `unsure`: true for close calls.
- `note`: why the label was chosen, in a few words.
- `abstract` (optional): stored only when both the row and Europe PMC give the licence as `cc-by` or `cc0`. Every other abstract is fetched from Europe PMC by PMID and cached outside the repo (`evals/abstracts.py`).

## How the papers were chosen
From the papers Triage had kept by 2026-11-12, grouped by publication type and abstract wording, then picked at random within each group: 15 indexed randomised trials, 15 indexed systematic reviews or meta-analyses, 15 likely observational studies, 7 likely animal and 3 likely lab studies, 2 likely narrative reviews, 2 likely non-randomised studies, 1 case report and 5 from the rest. Four edge cases were added by hand: two single-group intervention studies, a randomised trial not indexed as one, and a single-arm observational follow-up. The groups were only a way to pick; every label comes from reading the abstract, so some papers ended up in other designs.

The 69 papers: 16 observational, 14 reviews, 14 randomised trials, 2 non-randomised trials, 5 animal, 5 lab, and 13 not gradable (8 narrative reviews, 2 interview-only studies, 2 protocols, 1 case report). Expected levels: 30 very low, 12 low, 12 moderate, 2 high.

## How the labels were settled
Labels were drafted from the abstracts using the Grader's prompt and the rules in `docs/agents.md`. A second labeller then graded every paper blind, from the same rules, without seeing the drafts. They agreed on 61 of 69 papers (60 kept as `agreement`); every level they both gave was within one of the other. Of the 8 splits:
- 5 were settled by the written rules (`reconciled`), such as a review that does report its certainty and an observational study raised for a clear dose-response.
- 3 were settled by two rules the repo owner set, which also changed one paper both labellers had agreed on (4 `owner-rule` rows in all):
  - Studies that only report what people said in interviews or focus groups aren't graded (`not_a_study`).
  - Cross-sectional studies, which measure people once, sit one level lower for design.

The prompt follows both rules.

## What the eval scores
On approved rows, each paper goes through production's path: the Grader's rules first, then the model through the production client, then the code that turns its reply into a grade.
- **Design label:** the share of papers given the right design category or the right "not gradable" reason. A failed call counts as a wrong label.
- **Mix-ups:** studies in people called animal or lab studies, or the reverse. A review of animal or lab studies counts as not in people. This is the worst error, because readers would see the wrong kind of evidence.
- **Level:** exact agreement and agreement within one level, on papers both the label and the Grader call gradable.
- **No-conflicts funding concerns:** how many funding concerns only say the authors have no conflicts, which isn't a concern. Reported, not checked.

## Running the eval
`uv run python -m evals.grader` from `workers/` prints the scores (`CLAUDE.md` has the options). Keep `--report` files outside the repo: the model's reasons and funding concerns may quote abstracts.

## In CI
The `grader-eval` workflow runs the eval with `--check` on pull requests that change the Grader prompt, the Grader, the model client or the evals, for about $0.05 a run. It compares the scores with `baseline.json`, which holds the scores only. The check fails, and so blocks merging, when:
- any study in people and animal or lab study are mixed up;
- more than 2 calls fail;
- the design label score or the share of levels within one falls more than 10 points below the baseline, or the share of exact levels more than 15 points.

A pull request that changes the dataset must refresh the baseline with `--write-baseline`, or the check fails. Refresh it too after a change that improves the scores. `--write-baseline` with `--prompt-root` writes a candidate prompt's scores, so use it only when that prompt is being shipped.

## Model comparison (2026-11-13)
Both models ran the prompt from #68 on all 69 approved papers (56 gradable). Haiku ran twice; the second run is the baseline.

| Model | Design labels right | Mix-ups | Levels exact | Levels within one | Failed calls | Cost per run |
|---|---|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 95.7%, 94.2% | 0, 0 | 69.1%, 72.7% | 98.2%, 96.4% | 0, 0 | $0.050, $0.050 |
| `anthropic/claude-sonnet-5.5` | 98.6% | 0 | 57.1% | 94.6% | 0 | $0.97 |

Haiku ships: it agrees with the labels on levels more often, and its misses are smaller, at a twentieth of the cost. Sonnet got one or two more design labels right. Both models grade lower than the labels when they miss, Sonnet more often: it took 11 of the 12 papers labelled low down to very low. In these runs OpenRouter refused every Sonnet 5.5 request with reasoning turned off ("Reasoning is mandatory for this endpoint"), so its run used low reasoning effort.

Neither model wrote a funding concern that only says there are no conflicts: Sonnet wrote one real concern, Haiku none.

## Harshness check (2026-11-13)
Production's first 1,000 articles and both models' eval misses graded lower than the labels. The reports, which now list each grade's starting level and moves, showed four causes:
- Cohort and other observational studies were lowered for design just for being observational (confounding, can't show which came first), which is why they start low. About 140 of the 345 observational studies graded in production. Cross-sectional studies still lower one level.
- Trials were lowered for blinding, allocation or dropouts the abstract didn't mention, and for results that weren't significant, on top of the size lowering that already counts imprecision.
- Duration was judged against long-term effects the paper didn't claim, such as a three-hour blood pressure study being "too short for long-term effects".
- Studies in healthy young adults were lowered for population for age alone. Population now lowers for age only when the outcome depends on it, such as bone loss, falls or muscle loss with age (repo owner's rule).

Reviews that report their own certainty were also lowered again by the model. The code now keeps the review's rating and stores the model's concerns at 0 levels.

| Prompt | Runs | Levels exact | Levels within one | Misses lower / higher than the label |
|---|---|---|---|---|
| Before (#72) | 3 | 66.7–72.7% | 96.3–96.4% | 14–18 / 0–2 |
| After | 4 | 72.7–85.7% | 96.2–100% | 7–8 / 2–3 (in the two runs with move details) |

Runs vary by up to 10 points on exact levels, so single runs are noisy. Design labels stayed within 91–96%, with no mix-ups.
