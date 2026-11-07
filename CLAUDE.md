# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this is
An automated pipeline and web app that turns newly published nutrition research into graded, plain-English summaries, published as a weekly email, a web archive and podcast episodes. Accuracy and traceability matter more than anything else. A wrong number or an unsupported claim is a production bug.

## Source of truth
- Architecture and technology decisions: `docs/adr/` (one ADR per decision, numbered, never edited after acceptance; supersede with a new ADR).
- If a requested change conflicts with an accepted ADR, stop and say so before writing code. Propose a new ADR instead.
- Private context may be loaded from `CLAUDE.local.md` and `docs/private/` (both gitignored). Never copy their contents into committed files, commit messages, issues, PR descriptions, PR comments, reviews, code comments or logs. `CLAUDE.md`, ADRs and code may still state product, editorial, compliance and technical requirements in their own words, but never pricing, competitors, positioning, roadmap, revenue targets or personal working habits.

## How to work
- Small, reviewable changes: one concern per PR, with tests for code changes. Leave the main branch deployable.
- Read the relevant code and ADRs before proposing changes. Ask before large refactors, new dependencies, schema changes or anything hard to reverse.
- Verify current external facts (API behaviour, rate limits, pricing, licences) against official documentation, not memory. Link the source in the PR or ADR.
- End each task with a short summary: what changed, how it was verified, what's next.

## Pull requests
- All work goes through a PR. Never push directly to `main` unless the repo owner explicitly asks.
- When a PR is opened or receives substantive pushes, run two separate reviewer agents:
  - **Quality reviewer:** the change is professional and production ready, covering code quality, best practices, security and accessibility.
  - **Integration reviewer:** the PR works well in the current project and does not introduce bugs.
- Report review findings to the repo owner in the session. Do not post them to GitHub unless asked.
- Reviewers label each finding blocking or non-blocking. Blocking means a real defect, such as a bug, a conflict, an incorrect statement, exposed private content or instructions that cannot be followed.
- Approvals are not required. Merge once both reviewers have reported on the latest substantive push, required checks pass, there are no blocking findings and nothing major needs the repo owner's input, then report any non-blocking findings for the owner to decide on.

## Stack
- TypeScript with strict mode and Next.js for the web app.
- Python with strict type checking for scheduled pipeline workers, evals, data tooling and operational scripts (ADR 0001).
- Postgres; schema changes only through migrations, which must be reversible or documented as not.
- Docker; images must build for both `linux/amd64` and `linux/arm64`.
- Cloudflare (DNS, CDN, R2 object storage), Stripe (billing), OpenRouter (LLM and TTS access).
- Changing any of the above requires an ADR.

<!-- Fill in once the repo has them:
## Commands
- Install:
- Dev server:
- Tests / evals:
- Lint / typecheck:
- Migrations:
-->

## Engineering standards
- **Reliability:** pipeline stages are idempotent and resumable; external calls have timeouts, retries with backoff and clear failure states. One bad paper must not fail a whole run.
- **Cost control:** every LLM/TTS call goes through a single client that records model, tokens, cost and latency. Respect per-run budget limits; fail closed when exceeded.
- **Observability:** trace each pipeline run and each model call; structured logs; alert on failures. Never log secrets, emails or payment data.
- **Security:** secrets only via environment variables (`.env` is gitignored; keep `.env.example` current). Validate all external input. Least-privilege credentials. Verify Stripe webhook signatures.
- **Evaluation:** prompts and model choices are code. Changes to them must pass the eval suite in CI (faithfulness, numeric accuracy, grading agreement, reading level, hype score). Regressions block merge.
- **Maintainability:** provider-specific code (LLM, TTS, email, storage) sits behind interfaces. Internal names stay generic, not tied to the product brand.

## Content rules (enforce in code, prompts and evals)
- Every published claim must be traceable to a specific source (DOI/PMID) and supported by its text. The fact-check and hype-detection stages are hard gates: nothing publishes with unresolved flags.
- Every study carries an evidence grade (design, size, duration, population, funding/conflicts). Observational and animal studies are labelled as such.
- Scope: nutrition, and exercise only for health outcomes (bone, muscle, falls, cardiometabolic, brain, longevity). Occasional genetics content, limited to gene–diet and gene–ageing research. No aesthetics, weight-loss transformations or sports-performance content.
- No medical advice. Every page and episode carries an "AI-generated, not medical advice" disclosure.
- No sponsorship, affiliate links or advertising from supplement or food companies.

## Licensing and copyright
- Store the licence for every article.
- Reuse full text only when it's CC BY or more permissive. Anything else (including CC BY-NC and paywalled content) is summarised in our own words from abstracts/metadata; never reproduce it.
- Attribute and link the DOI on every summary.

## Privacy
- Collect only what's needed to run accounts and billing: email address and the Stripe customer reference.
- Never collect, infer or store users' health, medical or genetic data.
- Design to the Australian Privacy Principles; support account deletion and data export.
- Billing follows Australian Consumer Law: clear pricing (AUD) and self-serve cancellation.
