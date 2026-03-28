from __future__ import annotations

from collections import defaultdict

from backend.models.schemas import ScrapedShoeData


class ShoeAggregator:
    """Step 3: Normalize and deduplicate scraped data into clean shoe entities."""

    CUSHIONING_MAP = {
        "max cushion": "max",
        "maximum": "max",
        "high cushion": "high",
        "high": "high",
        "moderate": "medium",
        "medium": "medium",
        "firm": "low",
        "low": "low",
    }

    STABILITY_MAP = {
        "supportive": "high",
        "stability": "high",
        "neutral": "neutral",
        "guidance": "medium",
        "mild stability": "medium",
    }

    def aggregate(self, scraped_items: list[ScrapedShoeData]) -> list[ScrapedShoeData]:
        grouped: dict[str, list[ScrapedShoeData]] = defaultdict(list)
        for item in scraped_items:
            key = self._dedupe_key(item)
            grouped[key].append(self._normalize_item(item))

        normalized: list[ScrapedShoeData] = []
        for key, items in grouped.items():
            normalized.append(self._merge_entries(key, items))
        return normalized

    def _dedupe_key(self, item: ScrapedShoeData) -> str:
        return f"{item.brand.strip().lower()}::{item.shoe_name.strip().lower()}"

    def _normalize_item(self, item: ScrapedShoeData) -> ScrapedShoeData:
        normalized_cushioning = self._normalize_label(
            item.cushioning, self.CUSHIONING_MAP
        )
        normalized_stability = self._normalize_label(item.stability, self.STABILITY_MAP)
        return item.model_copy(
            update={
                "cushioning": normalized_cushioning,
                "stability": normalized_stability,
            }
        )

    def _normalize_label(
        self, value: str | None, mapping: dict[str, str]
    ) -> str | None:
        if value is None:
            return None
        lowered = value.strip().lower()
        return mapping.get(lowered, lowered)

    def _merge_entries(self, key: str, items: list[ScrapedShoeData]) -> ScrapedShoeData:
        first = items[0]
        pros = sorted({pro for item in items for pro in item.pros})
        cons = sorted({con for item in items for con in item.cons})

        # Keep the best-known values across duplicates.
        merged = first.model_copy(
            update={
                "cushioning": self._pick_most_specific([i.cushioning for i in items]),
                "stability": self._pick_most_specific([i.stability for i in items]),
                "weight_grams": self._pick_min([i.weight_grams for i in items]),
                "price_usd": self._pick_min([i.price_usd for i in items]),
                "pros": pros,
                "cons": cons,
            }
        )
        _ = key
        return merged

    def _pick_most_specific(self, values: list[str | None]) -> str | None:
        filtered = [value for value in values if value]
        if not filtered:
            return None
        priority = {"low": 1, "medium": 2, "neutral": 2, "high": 3, "max": 4}
        return max(filtered, key=lambda value: priority.get(value, 0))

    def _pick_min(self, values: list[int | float | None]) -> int | float | None:
        filtered = [value for value in values if value is not None]
        if not filtered:
            return None
        return min(filtered)
