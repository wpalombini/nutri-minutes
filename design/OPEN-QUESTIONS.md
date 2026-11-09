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

## For the Evidence Grader and the pipeline
- **Starting points.** Do the fixed "Why this grade" sentences match the Evidence Grader's rules: trials start high, observational studies low, animal and lab studies very low, reviews from the studies they combine? ([Why this grade](components/why-this-grade.md#content))
- **Designs outside the five labels.** How do non-randomised trials and Mendelian randomisation studies map to the five design categories? ([Study design label](components/study-design-label.md#content))
- **Repeated limits.** The app adds a fixed first limit for observational, animal and lab studies. Should the writer avoid repeating it? ([Limits block](components/limits-block.md#purpose-and-content))
- **One outcome per study.** The specs draw one main interval per summary. Do some summaries need a second one?

## Data no planned stage produces yet
The specs need these fields, but none of the stages in [`docs/agents.md`](../docs/agents.md) or the tables planned in [`docs/database.md`](../docs/database.md#tables-to-come) produce them:
- **Retraction and correction notice dates.** `article_relations` records that a retraction or erratum exists and the notice's source and ID, but not the notice's date. The link can be built from `target_id` when the target is a PubMed record (`target_source` `MED`); other sources would need their own rule. ([Study page](screens/study.md#data-a-summary))
- **`rechecked`:** whether a summary has been checked again after a correction. No stage re-checks summaries yet.
- **Editions:** the week's set of findings, its order and its publication date. The Editor chooses and orders findings, but nothing stores an edition the web app can read. ([Home](screens/home.md#data))
- **Topic descriptions and summary counts.** ([Topics](screens/topics.md#data))
- **Primary topic** for each summary. Triage may produce topic tags, but nothing picks one primary topic for rows and the study page's topic link. ([Finding row](components/finding-row.md#data-a-summary-list-item))

## Topic coverage
The scope is all of nutrition, plus exercise for health outcomes. The seven topics cover bone, muscle, falls, heart and metabolism, brain, longevity, and genes and diet. A nutrition study outside them, for example on gut health, cancer or pregnancy, would have no topic, no topic link and no archive page. Who decides whether to add topics, or a catch-all topic, and what rows show meanwhile? ([Topics](screens/topics.md#topic-list))
