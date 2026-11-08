# Open questions

Questions raised by the [screen](screens/README.md) and [component](components/README.md) specs that the specs can't settle on their own. Each says who it's waiting on. Remove an item once it's decided, and update the spec it points to.

## Pending the owner
- **Footer no-advertising line.** The footer adds "No advertising, sponsorship or affiliate links." after the disclosure. Keep it or drop it? ([App shell](screens/app-shell.md#footer))
- **Retracted studies.** The study page keeps a retracted study's summary published, with a notice before the headline, and rows show "Retracted". Should retracted summaries stay published like this, or be unpublished? ([Study page](screens/study.md#retraction-and-correction-notices))
- **Who writes the page copy.** "How we grade", "How summaries are made" and the seven topic descriptions have no text yet. The descriptions in the wireframes are samples. ([App shell](screens/app-shell.md#prose-page-template), [Topics](screens/topics.md#topic-list))
- **PMID without a DOI.** Every summary must show a DOI, and the app treats a summary without one as invalid. If a later source gives a PMID but no DOI, what should happen? ([Study at a glance](components/study-at-a-glance.md#states))
- **Changes to the approved plan, to accept or trim:**
  - The at-a-glance panel renames "Funding" to "Funding and conflicts" and adds Journal, Paper published, Summary published and Summarised from. ([Study at a glance](components/study-at-a-glance.md#content-in-order))
  - "Why this grade" uses "Raises certainty" and "Lowers certainty" in place of "confidence". ([Why this grade](components/why-this-grade.md#content))
  - A trial or review with no limits listed is treated as invalid, which is stricter than the content rules require. ([Limits block](components/limits-block.md#states))

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
