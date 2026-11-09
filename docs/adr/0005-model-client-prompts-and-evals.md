# ADR 0005: One model client, prompts as code and evals

- **Status:** Accepted
- **Date:** 2026-11-09

## Context
Scout is plain code. Triage, the next agent, and most agents after it call language models. `CLAUDE.md` already sets the rules: models are reached through OpenRouter, every call goes through a single client that records model, usage, cost and latency, each run has a budget and fails closed when it's spent, each call is traced, and prompts and model choices are code that must pass an eval suite. This ADR decides how those rules are built, before the first agent depends on them. It covers text models. Text-to-speech and speech-to-text will go through the same client, and their providers get their own ADRs.

Facts about OpenRouter were checked against its documentation on 2026-11-09 (see References):
- Chat Completions responses include `usage.cost` by default, along with token counts, cached tokens and reasoning tokens. The response schema calls the unit "credits", while the generation stats endpoint reports `total_cost` in US dollars.
- Structured outputs take a JSON Schema through `response_format`, and `provider.require_parameters` limits routing to providers that support it. The documentation warns that some providers treat the schema as a hint, so `strict` is not a guarantee.
- Routing can exclude providers that may store or train on request data (`provider.data_collection: "deny"`) and cap the price per million tokens (`provider.max_price`). A request that no provider can serve within those limits fails instead of running elsewhere.
- Model IDs are explicit and versioned, such as `anthropic/claude-haiku-5.5`. Floating aliases also exist. A `models` array falls back to other models on errors.
- Errors: 402 means insufficient credits, 408 a timeout, 429 a rate limit, and 502 and 503 an unavailable model or no provider that meets the routing rules. 429 and 503 may carry `Retry-After`. An error can also arrive in the body of a 200 response.
- API keys can have their own credit limit.

## Decision

### The client
- **One interface, one provider behind it.** Workers call a `ModelClient` interface in `workers/src/pipeline/models/`. The first implementation calls OpenRouter's Chat Completions endpoint with `httpx`, which the workers already depend on, so no SDK is added. Tests use a fake implementation, never the network.
- **One call shape.** A call names its stage, the article it's for (when there is one), the prompt, and the input values. The client renders the prompt, sends it, validates the reply and returns a typed result. Agents never build requests themselves.
- **Structured output only.** Every prompt defines a JSON Schema for its reply. The client sends it with `strict: true` and `require_parameters: true`, then validates the reply locally anyway. A reply that doesn't match the schema counts as a failed attempt.
- **Routing.** Requests set `data_collection: "deny"` and a `max_price` from the prompt's settings. Provider fallback within the same model is allowed. Model fallback (the `models` array) and floating aliases are not used, because they would change outputs without an eval.
- **Timeouts and retries.** Every request has a timeout. 408, 429, 5xx and errors in a 200 body are retried with exponential backoff, honouring `Retry-After`, up to a small fixed number of attempts. 400, 401 and 403 are not retried. 402 stops the run as failed, like a spent budget.

### Budgets
- **Per run, per stage.** Each stage has a budget in US dollars for one run, set by an environment variable with a default in code.
- **Checked before each call.** Before sending, the client works out the call's worst-case cost from the prompt length, the reply's `max_tokens` and the `max_price` caps. If the run's recorded spend plus that worst case would exceed the budget, the call is refused and the run stops as failed. The worst case is an upper bound, so a run can't overspend even if the reported cost arrives late or not at all.
- **Recorded after each call.** The spend added to the run is the cost the response reports. The client treats it as US dollars; the first implementation confirms that against the generation stats endpoint and records the result in `docs/agents.md`.
- **A backstop outside the code.** The production and CI API keys each have an OpenRouter credit limit, set by the repo owner.

### Tracing
- **A row per call.** Each attempt is stored in a `model_calls` table with the run, stage and article, the prompt name and version, the model requested and the model and provider that answered, the OpenRouter generation ID, the token counts, the cost, the latency, the outcome and any error. The table is added in its own migration with the client, following ADR 0002.
- **Outputs point to their call.** Each agent's output rows reference the call that produced them, which gives the model and prompt version that ADR 0002's traceability rule requires.
- **Logs.** Calls also emit structured log lines keyed by run and call. Logs and the table never hold API keys. Prompts and replies may hold abstracts and metadata, which are public, but never reader data.

### Prompts as code
- **Files in the repo.** Each prompt lives in `workers/src/pipeline/prompts/<stage>/` as a template plus a settings file with the model ID, parameters, `max_tokens`, price caps and reply schema.
- **Versioned by content.** A prompt's version is a hash of its template and settings, computed at load time, so any change to the prompt or its model gives a new version with nothing to bump by hand.
- **No prompts elsewhere.** Agents load prompts by name. Prompt text in agent code fails review.

### Evals
- **Where they live.** The eval suite is Python, in `workers/evals/`, with one suite per agent, each with a labelled dataset and metrics. Triage is scored on scope decisions and topic tags against labelled papers. The Evidence Grader is scored on agreement with hand-labelled grades. Later agents add the metrics `CLAUDE.md` lists: faithfulness, numeric accuracy, reading level and hype.
- **Labels.** Datasets hold article identifiers, the abstract and metadata Scout stored, and the expected labels. Abstracts are reproduced only when the article's licence permits it; otherwise the dataset stores the identifier and the eval fetches the abstract from Europe PMC on first use and caches it outside the repo.
- **When they run.** In CI, a pull request that changes a prompt, a model setting, the client or an eval runs the affected suites against the real models, with a CI-only OpenRouter key stored as a repository secret. Each suite has its own budget, and a run that hits it fails. Pull requests from forks don't get the secret and can't change prompts without a maintainer re-running the suite.
- **Baselines.** Each suite's latest accepted scores are committed in the repo. A score below its baseline by more than the suite's set tolerance fails the check and blocks merge. A change that improves scores updates the baseline in the same pull request.
- **Model choice.** A stage changes model by changing its settings file, which runs its eval. The cheapest model that meets the baseline is preferred.

## Consequences
- **One place to change providers.** Moving away from OpenRouter, or adding a direct provider, means a new `ModelClient` implementation and an ADR, not edits across agents.
- **Spend is bounded twice.** The client refuses calls that could exceed a run's budget, and key credit limits cap total spend if the client has a bug.
- **Prompt changes cost money to test.** Each prompt or model change runs real model calls in CI. Suites are sized so a run costs little, and only affected suites run.
- **Datasets are work.** Every agent with a model needs a labelled dataset before its prompt can merge. The repo owner decides the labels for grading.
- **No live calls in unit tests.** The fake client keeps `uv run pytest` free and offline. Live behaviour is covered by the evals.
- **Stricter routing may fail requests.** `data_collection: "deny"`, `require_parameters` and price caps can leave no provider for a model. The call then fails with a clear error instead of silently running elsewhere.
- **More storage.** One row per attempt in `model_calls`, kept with the outputs they trace.

## Alternatives considered
- **An SDK** (OpenAI's Python SDK pointed at OpenRouter, or a multi-provider library such as LiteLLM): less request code, but a new dependency whose retries, routing and cost handling would have to be overridden to meet the budget and tracing rules.
- **Recording cost from the generation stats endpoint for every call:** it reports cost in US dollars with more detail, but adds a second request per call. It is used to check the unit, not on every call.
- **Model fallbacks for availability:** fewer failed calls, but outputs would come from a model the evals didn't cover.
- **Evals on a schedule instead of in CI:** cheaper, but a regression could merge before it's caught, which `CLAUDE.md` rules out.
- **Recorded model replies in CI instead of live calls:** free and deterministic, but they can't test a changed prompt or model, which is the point of the suite.

## References
- [OpenRouter API overview](https://openrouter.ai/docs/api-reference/overview)
- [Usage accounting](https://openrouter.ai/docs/use-cases/usage-accounting)
- [Get a generation](https://openrouter.ai/docs/api-reference/get-a-generation)
- [Structured outputs](https://openrouter.ai/docs/features/structured-outputs)
- [Provider routing](https://openrouter.ai/docs/features/provider-routing)
- [Model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks)
- [Errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging.md)
- [API keys and limits](https://openrouter.ai/docs/api-reference/limits)
