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

The 69 papers: 16 observational, 14 reviews, 14 randomised trials, 2 non-randomised trials, 5 animal, 5 lab, and 13 not gradable (8 narrative reviews, 2 interview-only studies, 2 protocols, 1 case report). Expected levels: 29 very low, 13 low, 12 moderate, 2 high.

## How the labels were settled
Labels were drafted from the abstracts using the Grader's prompt and the rules in `docs/agents.md`. A second labeller then graded every paper blind, from the same rules, without seeing the drafts. They agreed on 61 of 69 papers; every level they both gave was within one of the other. Of the 8 splits:
- 5 were settled by the written rules (`reconciled`), such as a review that does report its certainty and an observational study raised for a clear dose-response.
- 3 were settled by two rules the repo owner set:
  - Studies that only report what people said in interviews or focus groups aren't graded (`not_a_study`).
  - Cross-sectional studies, which measure people once, sit one level lower for design.

The prompt follows both rules. A paid expert is planned to spot-check a sample of grades before launch.

## What the eval will score
The runner isn't built yet. It will score, on approved rows:
- **Design label:** the share of papers given the right design category or the right "not gradable" reason. Calling an animal or lab study a study in people, or the reverse, is the worst error.
- **Level:** exact agreement and agreement within one level, on papers where both the expected and the model's answer are gradable.
