from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.models.schemas import RecommendationRequest, RecommendationResponse
from backend.services.recommendation_pipeline import RecommendationPipeline
from backend.services.shoe_repository import SupabaseShoeRepository

router = APIRouter(tags=["recommendations"])
logger = logging.getLogger(__name__)


def _build_pipeline() -> RecommendationPipeline:
    logger.info("recommendations._build_pipeline called")
    shoe_repository = SupabaseShoeRepository()
    return RecommendationPipeline(shoe_repository)


pipeline = _build_pipeline()


@router.post("/recommend-shoes", response_model=RecommendationResponse)
async def recommend_shoes(payload: RecommendationRequest) -> RecommendationResponse:
    logger.info(
        "recommendations.recommend_shoes called shoe_type=%s budget=%s max_results=%s",
        payload.shoe_type.value,
        payload.budget,
        payload.max_results,
    )
    try:
        return pipeline.recommend(payload)
    except Exception as exc:
        logger.exception("recommendations.recommend_shoes failed: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Failed to build recommendation: {exc}"
        ) from exc
