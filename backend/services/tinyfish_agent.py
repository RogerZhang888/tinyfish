from __future__ import annotations

from collections.abc import Iterable
import os
import random

from backend.models.schemas import RecommendationRequest, ScrapePlan, ScrapedShoeData


MOCK_SHOE_DB: list[dict] = [
    {
        "shoe_name": "Novablast 5",
        "brand": "ASICS",
        "cushioning": "high",
        "stability": "neutral",
        "weight_grams": 252,
        "use_case": "daily trainer",
        "price_usd": 140,
        "foot_shape_fit": "neutral",
        "pros": ["Bouncy ride", "Great value"],
        "cons": ["Softer heel may feel unstable for some"],
    },
    {
        "shoe_name": "Gel-Kayano 31",
        "brand": "ASICS",
        "cushioning": "max",
        "stability": "high",
        "weight_grams": 303,
        "use_case": "long run",
        "price_usd": 165,
        "foot_shape_fit": "wide",
        "pros": ["Excellent support", "Comfortable over long mileage"],
        "cons": ["Heavier than neutral trainers"],
    },
    {
        "shoe_name": "Adizero Boston 13",
        "brand": "Adidas",
        "cushioning": "medium",
        "stability": "neutral",
        "weight_grams": 267,
        "use_case": "tempo",
        "price_usd": 160,
        "foot_shape_fit": "narrow",
        "pros": ["Fast turnover", "Versatile training shoe"],
        "cons": ["Firm feel at easy pace"],
    },
    {
        "shoe_name": "Alphafly 3",
        "brand": "Nike",
        "cushioning": "max",
        "stability": "neutral",
        "weight_grams": 218,
        "use_case": "racer",
        "price_usd": 285,
        "foot_shape_fit": "narrow",
        "pros": ["Elite race performance", "Explosive rebound"],
        "cons": ["Premium price", "Not ideal for daily running"],
    },
    {
        "shoe_name": "Vomero 18",
        "brand": "Nike",
        "cushioning": "max",
        "stability": "neutral",
        "weight_grams": 300,
        "use_case": "daily trainer",
        "price_usd": 160,
        "foot_shape_fit": "wide",
        "pros": ["Very plush underfoot", "Smooth easy-day ride"],
        "cons": ["Not the lightest option"],
    },
    {
        "shoe_name": "Endorphin Speed 5",
        "brand": "Saucony",
        "cushioning": "high",
        "stability": "neutral",
        "weight_grams": 229,
        "use_case": "racer",
        "price_usd": 170,
        "foot_shape_fit": "neutral",
        "pros": ["Snappy and lightweight", "Great for workouts"],
        "cons": ["Upper can feel snug for wide feet"],
    },
    {
        "shoe_name": "Ghost Max 3",
        "brand": "Brooks",
        "cushioning": "max",
        "stability": "medium",
        "weight_grams": 289,
        "use_case": "long run",
        "price_usd": 155,
        "foot_shape_fit": "wide",
        "pros": ["Stable rocker", "Protective cushioning"],
        "cons": ["Less agile for speed sessions"],
    },
    {
        "shoe_name": "Hoka Mach X 3",
        "brand": "HOKA",
        "cushioning": "high",
        "stability": "neutral",
        "weight_grams": 242,
        "use_case": "tempo",
        "price_usd": 190,
        "foot_shape_fit": "neutral",
        "pros": ["Fast and fun ride", "Responsive midsole"],
        "cons": ["Can feel narrow in forefoot"],
    },
    {
        "shoe_name": "Peregrine 15",
        "brand": "Saucony",
        "cushioning": "medium",
        "stability": "high",
        "weight_grams": 277,
        "use_case": "trail",
        "price_usd": 145,
        "foot_shape_fit": "neutral",
        "pros": ["Great grip", "Secure upper"],
        "cons": ["Firm on road transitions"],
    },
]


class TinyFishScraperAgent:
    """Step 2: TinyFish integration point.

    This MVP uses deterministic mock data while preserving the same interface
    expected by a future real TinyFish browser automation client.
    """

    def __init__(self) -> None:
        # Set TINYFISH_API_KEY in backend/.env (or shell env) when replacing mock logic.
        self.api_key = os.getenv("TINYFISH_API_KEY")

    def scrape(
        self, plan: ScrapePlan, user_input: RecommendationRequest
    ) -> list[ScrapedShoeData]:
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
        del goal  # Placeholder until real prompt-driven extraction is wired.

        candidates = [
            shoe
            for shoe in MOCK_SHOE_DB
            if shoe["price_usd"] <= user_input.budget * 1.15
        ]
        if not candidates:
            candidates = MOCK_SHOE_DB.copy()

        # Bias selection toward intended use, but keep some diversity like real web data.
        preferred = [
            shoe
            for shoe in candidates
            if shoe["use_case"] == user_input.shoe_type.value
        ]
        pool = preferred + candidates
        random.seed(f"{source_url}:{user_input.shoe_type.value}:{user_input.budget}")
        sample_size = min(6, len(pool))
        sampled = random.sample(pool, sample_size)

        for shoe in sampled:
            yield ScrapedShoeData(
                **shoe,
                source=source_url,
            )
