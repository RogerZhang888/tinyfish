from __future__ import annotations

from backend.models.schemas import (
    PipelineMetadata,
    RecommendationRequest,
    RecommendationResponse,
)
from backend.services.aggregator import ShoeAggregator
from backend.services.planner import QueryPlanner
from backend.services.ranker import ShoeRanker
from backend.services.tinyfish_agent import TinyFishScraperAgent


class RecommendationPipeline:
    """Orchestrates Planner -> TinyFish Agent -> Aggregator -> Ranker."""

    def __init__(
        self,
        planner: QueryPlanner,
        tinyfish_agent: TinyFishScraperAgent,
        aggregator: ShoeAggregator,
        ranker: ShoeRanker,
    ) -> None:
        self.planner = planner
        self.tinyfish_agent = tinyfish_agent
        self.aggregator = aggregator
        self.ranker = ranker

    def recommend(self, user_input: RecommendationRequest) -> RecommendationResponse:
        plan = self.planner.create_plan(user_input)
        scraped_items = self.tinyfish_agent.scrape(plan, user_input)
        normalized_items = self.aggregator.aggregate(scraped_items)
        ranked_items = self.ranker.rank(user_input, normalized_items)

        return RecommendationResponse(
            recommendations=ranked_items,
            metadata=PipelineMetadata(
                targets_planned=len(plan.targets),
                items_scraped=len(scraped_items),
                items_normalized=len(normalized_items),
            ),
        )
