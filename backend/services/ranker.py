from __future__ import annotations

import logging

from backend.models.schemas import (
    RecommendationItem,
    RecommendationRequest,
    ScrapedShoeData,
)
from backend.services.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class ShoeRanker:
    """Step 4: Score shoes against user profile, then optionally refine via LLM."""

    def __init__(self, openai_client: OpenAIClient) -> None:
        self.openai_client = openai_client

    def rank(
        self,
        user_input: RecommendationRequest,
        shoes: list[ScrapedShoeData],
    ) -> list[RecommendationItem]:
        logger.info("ShoeRanker.rank called shoes=%s", len(shoes))
        try:
            scored_candidates: list[dict] = []
            for shoe in shoes:
                score = self._score_shoe(user_input, shoe)
                scored_candidates.append(
                    {
                        "name": shoe.shoe_name,
                        "brand": shoe.brand,
                        "score": score,
                        "reason": self._build_reason(user_input, shoe, score),
                        "best_for": self._best_for(user_input, shoe),
                        "key_features": OpenAIClient.feature_summary(shoe),
                        "sources": [str(shoe.source)],
                    }
                )

            scored_candidates.sort(key=lambda item: item["score"], reverse=True)
            top_candidates = scored_candidates[: user_input.max_results]
            logger.info("ShoeRanker.rank top_candidates=%s", len(top_candidates))

            llm_refined = self.openai_client.rerank_recommendations(
                user_input, top_candidates
            )
            final_candidates = llm_refined if llm_refined else top_candidates
            logger.info("ShoeRanker.rank final_candidates=%s", len(final_candidates))

            return [RecommendationItem(**candidate) for candidate in final_candidates]
        except Exception as exc:
            logger.exception("ShoeRanker.rank failed: %s", exc)
            raise

    def _score_shoe(
        self, user_input: RecommendationRequest, shoe: ScrapedShoeData
    ) -> int:
        logger.info(
            "ShoeRanker._score_shoe called brand=%s shoe_name=%s",
            shoe.brand,
            shoe.shoe_name,
        )
        score = 45

        if shoe.use_case == user_input.shoe_type.value:
            score += 20

        if shoe.price_usd is not None:
            if shoe.price_usd <= user_input.budget:
                score += 15
            elif shoe.price_usd <= user_input.budget * 1.1:
                score += 5
            else:
                score -= 10

        preference_set = {pref.strip().lower() for pref in user_input.preferences}

        if "high cushioning" in preference_set and shoe.cushioning in {"high", "max"}:
            score += 8
        if "stability" in preference_set and shoe.stability in {"medium", "high"}:
            score += 8
        if (
            "lightweight" in preference_set
            and shoe.weight_grams
            and shoe.weight_grams <= 245
        ):
            score += 8
        if "good lacing" in preference_set and any(
            "upper" in pro.lower() or "secure" in pro.lower() for pro in shoe.pros
        ):
            score += 5

        if user_input.foot_shape == "wide" and shoe.foot_shape_fit == "wide":
            score += 6
        if user_input.foot_shape == "narrow" and shoe.foot_shape_fit == "narrow":
            score += 6

        if user_input.weekly_mileage_km >= 50 and shoe.use_case in {
            "long run",
            "daily trainer",
        }:
            score += 5

        return max(0, min(100, score))

    def _build_reason(
        self, user_input: RecommendationRequest, shoe: ScrapedShoeData, score: int
    ) -> str:
        logger.info(
            "ShoeRanker._build_reason called brand=%s shoe_name=%s score=%s",
            shoe.brand,
            shoe.shoe_name,
            score,
        )
        parts = [f"Score {score} based on use-case, budget, and profile fit."]
        if shoe.use_case == user_input.shoe_type.value:
            parts.append("Matches your requested shoe category.")
        if shoe.price_usd and shoe.price_usd <= user_input.budget:
            parts.append("Fits within budget.")
        if shoe.cushioning in {"high", "max"}:
            parts.append("Offers strong impact protection for consistent training.")
        if shoe.stability in {"medium", "high"}:
            parts.append("Provides additional guidance and control.")
        return " ".join(parts)

    def _best_for(
        self, user_input: RecommendationRequest, shoe: ScrapedShoeData
    ) -> str:
        logger.info(
            "ShoeRanker._best_for called brand=%s shoe_name=%s",
            shoe.brand,
            shoe.shoe_name,
        )
        if shoe.use_case == "trail":
            return "Trail sessions and uneven terrain"
        if user_input.experience_level == "beginner":
            return "Comfort-first training and consistent weekly mileage"
        if shoe.use_case == "racer":
            return "Workouts and race-day efforts"
        if shoe.use_case == "long run":
            return "High-mileage long runs and recovery days"
        return "Daily runs with balanced comfort and responsiveness"
