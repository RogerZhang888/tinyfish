from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models.schemas import RecommendationRequest, RecommendationResponse
from backend.services.aggregator import ShoeAggregator
from backend.services.openai_client import OpenAIClient
from backend.services.planner import QueryPlanner
from backend.services.ranker import ShoeRanker
from backend.services.recommendation_pipeline import RecommendationPipeline
from backend.services.tinyfish_agent import TinyFishScraperAgent

router = APIRouter(tags=["recommendations"])


def _build_pipeline() -> RecommendationPipeline:
    openai_client = OpenAIClient()
    planner = QueryPlanner(openai_client)
    tinyfish_agent = TinyFishScraperAgent()
    aggregator = ShoeAggregator()
    ranker = ShoeRanker(openai_client)
    return RecommendationPipeline(planner, tinyfish_agent, aggregator, ranker)


pipeline = _build_pipeline()


@router.post("/recommend-shoes", response_model=RecommendationResponse)
async def recommend_shoes(payload: RecommendationRequest) -> RecommendationResponse:
    try:
        return pipeline.recommend(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to build recommendation: {exc}"
        ) from exc
