"""Check the unit of OpenRouter's reported cost: `python -m pipeline.models.check_cost`.

Makes one tiny call through the client, then reads the same generation from the generation
stats endpoint, which reports `total_cost` in US dollars. If the two match, the cost the client
records is in US dollars. Needs `OPENROUTER_API_KEY`. Costs a fraction of a cent, and nothing is
written to the database.
"""

import logging
import sys
import time
from decimal import Decimal

import httpx

from pipeline.models.calls import MemoryCallLog
from pipeline.models.client import CallRequest, ModelCallError, StopRun
from pipeline.models.openrouter import OpenRouterClient, OpenRouterSettings
from pipeline.models.prompts import load_prompt

GENERATION_URL = "https://openrouter.ai/api/v1/generation"
BUDGET_USD = Decimal("0.01")
LOOKUP_ATTEMPTS = 5


def _generation_cost(api_key: str, generation_id: str) -> Decimal | None:
    """`total_cost` for the generation. Stats can take a moment to appear, so 404s are retried."""
    with httpx.Client(timeout=30.0, headers={"Authorization": f"Bearer {api_key}"}) as http:
        for attempt in range(1, LOOKUP_ATTEMPTS + 1):
            try:
                response = http.get(GENERATION_URL, params={"id": generation_id})
            except httpx.TransportError as exc:
                print(f"Generation lookup failed: {type(exc).__name__}")
                return None
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                data = body.get("data") if isinstance(body, dict) else None
                cost = data.get("total_cost") if isinstance(data, dict) else None
                if isinstance(cost, bool) or not isinstance(cost, int | float):
                    print("The generation had no total_cost")
                    return None
                return Decimal(str(cost))
            if response.status_code != 404 or attempt == LOOKUP_ATTEMPTS:
                print(f"Generation lookup failed with HTTP {response.status_code}")
                return None
            time.sleep(2.0 * attempt)
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = OpenRouterSettings.from_env()
    prompt = load_prompt("diagnostics/cost_check")
    with OpenRouterClient(
        settings, log=MemoryCallLog(), budgets={prompt.stage: BUDGET_USD}
    ) as client:
        try:
            result = client.call(CallRequest(run_id=0, prompt=prompt, inputs={"word": "ready"}))
        except (ModelCallError, StopRun) as exc:
            print(f"The call failed: {exc}")
            return 1
    if result.generation_id is None or result.cost_usd is None:
        print("The response had no generation ID or no cost")
        return 1
    total = _generation_cost(settings.api_key, result.generation_id)
    print(f"model: {result.model}")
    print(f"usage.cost from the response: {result.cost_usd}")
    print(f"total_cost (USD) from the generation endpoint: {total}")
    if total is None:
        return 1
    if total == result.cost_usd:
        print("They match: usage.cost is in US dollars.")
        return 0
    print("They differ: don't treat usage.cost as US dollars until this is explained.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
