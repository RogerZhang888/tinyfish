from __future__ import annotations

from collections.abc import Iterable
import json
import logging
import os
from urllib import error, request

from backend.models.schemas import RecommendationRequest, ScrapePlan, ScrapedShoeData

logger = logging.getLogger(__name__)


class TinyFishScraperAgent:
    """Step 2: TinyFish integration point.

    This MVP uses deterministic mock data while preserving the same interface
    expected by a future real TinyFish browser automation client.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("TINYFISH_API_KEY")
        self.base_url = os.getenv(
            "TINYFISH_BASE_URL", "https://agent.tinyfish.ai/v1/automation/run"
        )

    def scrape(
        self, plan: ScrapePlan, user_input: RecommendationRequest
    ) -> list[ScrapedShoeData]:
        if not self.api_key:
            raise ValueError("TINYFISH_API_KEY is not configured")

        scraped_items: list[ScrapedShoeData] = []
        for target in plan.targets:
            target_items = self._scrape_target(
                source_url=str(target.url),
                goal=target.goal,
                user_input=user_input,
            )
            scraped_items.extend(target_items)
        return scraped_items

    def _scrape_target(
        self,
        source_url: str,
        goal: str,
        user_input: RecommendationRequest,
    ) -> Iterable[ScrapedShoeData]:
        payload = {
            "url": source_url,
            "goal": self._build_goal(goal, user_input),
            "browser_profile": "lite",
            "proxy_config": {
                "enabled": True,
                "country_code": "US",
            },
            "api_integration": "runwise",
        }

        logger.info("Calling TinyFish automation url=%s", source_url)
        response = self._post_json(payload)

        if response.get("status") != "COMPLETED":
            raise ValueError(
                f"TinyFish run failed for {source_url}: {response.get('error')}"
            )

        for shoe in self._extract_shoes(response.get("result"), source_url):
            yield shoe

    def _build_goal(self, goal: str, user_input: RecommendationRequest) -> str:
        return (
            f"{goal}. Extract shoes relevant to this runner profile: "
            f"{user_input.model_dump_json()}. "
            "Return strict JSON only with shape "
            '{"shoes":[{"shoe_name":"","brand":"","cushioning":"","stability":"",'
            '"weight_grams":0,"use_case":"","price_usd":0,"foot_shape_fit":"",'
            '"pros":[],"cons":[]}]} '
            "Use null for unknown scalar fields and [] for unknown pros/cons."
        )

    def _post_json(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=90) as resp:
                raw_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ValueError(
                f"TinyFish request failed with status {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise ValueError(f"TinyFish request could not be completed: {exc}") from exc

        parsed = json.loads(raw_body)
        if not isinstance(parsed, dict):
            raise ValueError("TinyFish response was not a JSON object")
        return parsed

    def _extract_shoes(
        self, result: object, source_url: str
    ) -> Iterable[ScrapedShoeData]:
        parsed_result = result
        if isinstance(parsed_result, str):
            parsed_result = json.loads(parsed_result)

        shoes_payload: list[dict] = []
        if isinstance(parsed_result, dict):
            raw_shoes = parsed_result.get("shoes")
            if isinstance(raw_shoes, list):
                shoes_payload = [item for item in raw_shoes if isinstance(item, dict)]
        elif isinstance(parsed_result, list):
            shoes_payload = [item for item in parsed_result if isinstance(item, dict)]

        if not shoes_payload:
            raise ValueError(f"TinyFish returned no shoe data for {source_url}")

        for shoe in shoes_payload:
            shoe_name = str(shoe.get("shoe_name") or shoe.get("name") or "").strip()
            brand = str(shoe.get("brand") or "").strip()
            if not shoe_name or not brand:
                continue
            yield ScrapedShoeData(
                shoe_name=shoe_name,
                brand=brand,
                cushioning=self._optional_text(shoe.get("cushioning")),
                stability=self._optional_text(shoe.get("stability")),
                weight_grams=self._optional_int(shoe.get("weight_grams")),
                use_case=self._optional_text(shoe.get("use_case")),
                price_usd=self._optional_float(shoe.get("price_usd")),
                foot_shape_fit=self._optional_text(shoe.get("foot_shape_fit")),
                pros=self._string_list(shoe.get("pros")),
                cons=self._string_list(shoe.get("cons")),
                source=source_url,
            )

    def _optional_text(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

    def _optional_float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return None

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
