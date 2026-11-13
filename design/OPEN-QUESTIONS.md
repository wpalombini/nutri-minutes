# Open questions

Questions raised by the [screen](screens/README.md) and [component](components/README.md) specs that the specs can't settle on their own. Each says who it's waiting on. Once an item is decided, update the spec it points to and move the item to the decided list.

## Decided by the owner (2026-11-09)
- The footer keeps the no-advertising line.
- Retracted studies stay published, with the retraction notice before the headline.
- We draft "How we grade", "How summaries are made" and the topic descriptions, and the owner approves them in a PR.
- A source with a PMID but no DOI links to its PubMed record instead.
- The theme control's legend is "Theme", and it stays in the footer for now. Later it should move to a settings page, where readers will also choose topics to follow.
- The privacy page, when written, says the theme choice is stored on the reader's device only.
- The plan changes are accepted: the extra at-a-glance rows and "Funding and conflicts", "Raises / Lowers certainty", and treating a trial or review with no limits as invalid.

## Decided by the owner (2026-11-12), with the Evidence Grader plan
- **Starting points.** The "Why this grade" sentences match the Grader: randomised trials start high; non-randomised trials and observational studies low; animal and lab studies very low; a review from what it combines (trials high, observational studies or a mix low, animal or lab studies very low), or from its own certainty rating when it reports one. ([Why this grade](components/why-this-grade.md#content))
- **Designs outside the five labels.** A sixth label, "Non-randomised trial", starting low. Mendelian randomisation studies are observational. Narrative reviews, case reports, study plans and interview-only studies aren't graded and get no summary. ([Study design label](components/study-design-label.md#content))
- **Repeated limits.** The Writer doesn't repeat the app's fixed first limit. Non-randomised trials get a fixed first limit too. ([Limits block](components/limits-block.md#purpose-and-content))
- **One outcome per study.** One grade and one main interval per summary, for the study's main outcome.

## For the Writer
- **A second outcome.** Do some summaries need a second outcome and interval? Decided when the Writer is planned.

## Settled by a built stage
- **Primary topic** for each summary: Triage stores one for each in-scope article as a topic slug (`triage_decisions.primary_topic`, [database](../docs/database.md#triage_decisions)). ([Finding row](components/finding-row.md#data-a-summary-list-item))

## Data no planned stage produces yet
The specs need these fields, but none of the stages in [`docs/agents.md`](../docs/agents.md) or the tables planned in [`docs/database.md`](../docs/database.md#tables-to-come) produce them:
- **Retraction and correction notice dates.** `article_relations` records that a retraction or erratum exists and the notice's source and ID, but not the notice's date. The link can be built from `target_id` when the target is a PubMed record (`target_source` `MED`); other sources would need their own rule. ([Study page](screens/study.md#data-a-summary))
- **`rechecked`:** whether a summary has been checked again after a correction. No stage re-checks summaries yet.
- **Editions:** the week's set of findings, its order and its publication date. The Editor chooses and orders findings, but nothing stores an edition the web app can read. ([Home](screens/home.md#data))
- **Topic descriptions and summary counts.** ([Topics](screens/topics.md#data))

## Topic coverage
The scope is nutrition and exercise research that bears on health (not sports performance or looks) and fits one of seven topics: bone, muscle, falls, heart and metabolism, brain, longevity, and genes and diet. Triage currently drops a nutrition study outside them, for example on gut health, cancer or pregnancy. Should the scope widen, who decides whether to add topics, or a catch-all topic, and what rows show meanwhile? ([Topics](screens/topics.md#topic-list))
