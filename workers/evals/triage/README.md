# Triage eval dataset

`dataset.jsonl` holds the papers the Triage eval scores the scope decision against (ADR 0005), one JSON object per line.

## Fields
- `pmid`, `doi`, `pmcid`: the paper's identifiers. Every paper has a PMID. The eval looks papers up by these, never by database ID, which differs between databases.
- `title`, `publication_types`: as Scout stored them, so the eval sends the model what production sends.
- `licence`: the licence code Scout recorded. The rule on abstracts below depends on it.
- `sample`: `random` for the random sample, `picked` for hand-picked papers.
- `expected`: the correct decision. `in_scope` is true or false. For an in-scope paper, `topics` lists every topic it fits, best first, and `primary_topic` is the first of them. For an out-of-scope paper, `topics` is empty and `primary_topic` is null.
- `label`: `suggested` until the row is reviewed, then `approved`. Only approved rows count towards scores.
- `reviewed_by`: how an approved label was settled. `owner`: the repo owner reviewed the paper. `owner-rule`: a rule the owner set for a kind of paper decided it. `agreement`: the suggested label and an independent blind labelling of the paper agreed. Absent while the label is `suggested`.
- `unsure`: true when the call is close enough that the owner should look at it first.
- `note`: why the label was chosen, in a few words. Required when `unsure` is true.
- `abstract` (optional): stored only when both the row and Europe PMC give the licence as `cc-by` or `cc0`, which is 55 rows. Every other abstract is fetched from Europe PMC by PMID and cached outside the repo (`evals/abstracts.py`).

## How the labels were settled
Labels were first suggested with a note on each close call. A second labeller then labelled every paper blind, from the scope rules alone, without seeing the suggestions. The two agreed on 131 of 140 papers. The repo owner reviewed 26 papers directly and settled the 9 disagreements, directly or with rules. Because Triage should keep a paper whenever it is unsure, the owner chose rules that only ever keep papers. 20 of the reviewed papers are recorded as `owner`; 10 papers that the rules settled or changed (6 reviewed, 4 others) are recorded as `owner-rule`:
- Nutritional status scores, such as the Geriatric Nutritional Risk Index, count as nutrition.
- A measured health outcome isn't required. Nutrition or exercise research that plausibly fits a topic, such as exercise physiology, physical function or a map of exercise research, is kept with a low relevance.
- Research on why muscle, mobility or physical activity declines with age is in scope, even without a diet or exercise exposure.

## How the papers were chosen
From the 2,566 papers Scout had stored by 2026-11-11 that pass Triage's rules (not retracted, research, with an abstract, in English), chosen in two ways:
- **60 at random.** They show the real mix, which is mostly out of scope: 10 of the 60 are in scope.
- **80 picked by hand.** Title searches found likely in-scope papers for each topic, then borderline papers: diet or exercise research outside the topics (athletes, pregnancy, children, cancer, animal feed), topic outcomes without a diet or exercise exposure (lab nutrition scores, drugs, herbal formulas), and papers that use a diet only to set up an animal model.

Missing an in-scope paper is the costlier mistake, so the eval will weigh missed in-scope papers most.
