from __future__ import annotations

import logging

from backend.models.schemas import (
    PipelineMetadata,
    RecommendationRequest,
    RecommendationResponse,
)
from backend.services.shoe_repository import SupabaseShoeRepository

logger = logging.getLogger(__name__)


class RecommendationPipeline:
    """Fetch recommendations from Supabase based on user filters."""

    def __init__(
        self,
        shoe_repository: SupabaseShoeRepository,
    ) -> None:
        self.shoe_repository = shoe_repository

    def recommend(self, user_input: RecommendationRequest) -> RecommendationResponse:
        logger.info("RecommendationPipeline.recommend called")
        try:
            recommendations = self.shoe_repository.search_shoes(user_input)
            logger.info(
                "RecommendationPipeline.recommend search_completed items=%s",
                len(recommendations),
            )

            return RecommendationResponse(
                recommendations=recommendations,
                metadata=PipelineMetadata(
                    targets_planned=1,
                    items_scraped=len(recommendations),
                    items_normalized=len(recommendations),
                ),
            )
        except Exception as exc:
            logger.exception("RecommendationPipeline.recommend failed: %s", exc)
            raise
