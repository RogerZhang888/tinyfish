from __future__ import annotations

import json
import os
from typing import Any

from backend.models.schemas import PlannedTarget, RecommendationRequest, ScrapedShoeData


class OpenAIClient:
    """Thin wrapper around OpenAI interactions with deterministic fallbacks for MVP mode."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def plan_targets(
        self, user_input: RecommendationRequest
    ) -> list[PlannedTarget] | None:
        """Return dynamic scrape targets suggested by the LLM, or None if unavailable."""
        if not self.enabled:
            return None

        prompt = (
            "You are planning web scraping targets for running shoe recommendations. "
            'Return strict JSON with shape: {"targets": [{"url": "https://...", '
            '"goal": "...", "source_type": "brand_site|review_blog|comparison_site|community"}]}. '
            f"User input: {user_input.model_dump_json()}"
        )

        try:
            response = self._client.responses.create(
                model=self.model,
                input=prompt,
                temperature=0.2,
            )
            raw_text = response.output_text
            parsed = json.loads(raw_text)
            targets = parsed.get("targets", [])
            return [PlannedTarget(**target) for target in targets]
        except Exception:
            return None

    def rerank_recommendations(
        self,
        user_input: RecommendationRequest,
        scored_shoes: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Optionally ask the LLM to refine explanations/ranking while preserving schema."""
        if not self.enabled:
            return None

        prompt = (
            "You are a running shoe expert. Given pre-scored candidates, "
            "return strict JSON list preserving fields name, brand, score, reason, best_for, key_features, sources. "
            "You may adjust score by at most +/-5 points and improve natural-language reason quality. "
            f"User profile: {user_input.model_dump_json()}\n"
            f"Candidates: {json.dumps(scored_shoes)}"
        )

        try:
            response = self._client.responses.create(
                model=self.model,
                input=prompt,
                temperature=0.3,
            )
            raw_text = response.output_text
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                return parsed
            return None
        except Exception:
            return None

    @staticmethod
    def feature_summary(shoe: ScrapedShoeData) -> list[str]:
        features: list[str] = []
        if shoe.cushioning:
            features.append(f"Cushioning: {shoe.cushioning}")
        if shoe.stability:
            features.append(f"Stability: {shoe.stability}")
        if shoe.weight_grams:
            features.append(f"Weight: {shoe.weight_grams}g")
        if shoe.use_case:
            features.append(f"Use case: {shoe.use_case}")
        return features
