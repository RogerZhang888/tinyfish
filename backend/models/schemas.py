from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ShoeType(str, Enum):
    DAILY_TRAINER = "daily trainer"
    RACER = "racer"
    LONG_RUN = "long run"
    TRAIL = "trail"
    TEMPO = "tempo"


class FootShape(str, Enum):
    WIDE = "wide"
    NARROW = "narrow"
    NEUTRAL = "neutral"


class RunningStyle(str, Enum):
    HEEL_STRIKE = "heel strike"
    MIDFOOT = "midfoot"
    FOREFOOT = "forefoot"


class ExperienceLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RecommendationRequest(BaseModel):
    budget: float = Field(gt=0, description="Budget in USD")
    shoe_type: ShoeType
    foot_shape: FootShape
    running_style: RunningStyle
    preferences: list[str] = Field(default_factory=list)
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    weekly_mileage_km: float = Field(ge=0)
    experience_level: ExperienceLevel
    max_results: int = Field(default=5, ge=1, le=10)


class PlannedTarget(BaseModel):
    url: HttpUrl
    goal: str
    source_type: Literal["brand_site", "review_blog", "comparison_site", "community"]


class ScrapePlan(BaseModel):
    targets: list[PlannedTarget]


class ScrapedShoeData(BaseModel):
    shoe_name: str
    brand: str
    cushioning: str | None = None
    stability: str | None = None
    weight_grams: int | None = None
    use_case: str | None = None
    price_usd: float | None = None
    foot_shape_fit: str | None = None
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    source: HttpUrl


class RecommendationItem(BaseModel):
    name: str
    brand: str
    score: int = Field(ge=0, le=100)
    key_features: list[str] = Field(default_factory=list)
    reason: str
    best_for: str
    sources: list[HttpUrl] = Field(default_factory=list)


class PipelineMetadata(BaseModel):
    targets_planned: int
    items_scraped: int
    items_normalized: int


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]
    metadata: PipelineMetadata
