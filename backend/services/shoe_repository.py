from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error, parse, request

from backend.models.schemas import RecommendationItem, RecommendationRequest


logger = logging.getLogger(__name__)


class SupabaseShoeRepository:
    """Fetch shoe recommendations from the Supabase shoes table."""

    def __init__(self) -> None:
        logger.info("SupabaseShoeRepository.__init__ called")
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.getenv("SUPABASE_API_KEY", "")
        timeout_value = os.getenv("SUPABASE_TIMEOUT_SECONDS", "30").strip()
        self.timeout_seconds = int(timeout_value or "30")

    def search_shoes(
        self, user_input: RecommendationRequest
    ) -> list[RecommendationItem]:
        logger.info("SupabaseShoeRepository.search_shoes called")
        if not self.base_url:
            raise ValueError("SUPABASE_URL is not configured")
        if not self.api_key:
            raise ValueError("SUPABASE_API_KEY is not configured")

        try:
            url = self._build_query_url(user_input)
            rows = self._fetch_rows(url)
            logger.info("SupabaseShoeRepository.search_shoes rows=%s", len(rows))
            return [self._row_to_recommendation(row, user_input) for row in rows]
        except Exception as exc:
            logger.exception("SupabaseShoeRepository.search_shoes failed: %s", exc)
            raise

    def _build_query_url(self, user_input: RecommendationRequest) -> str:
        logger.info("SupabaseShoeRepository._build_query_url called")
        budget_filter = self._format_numeric_filter(user_input.budget)
        query_params: list[tuple[str, str]] = [
            ("select", "*"),
            ("price", f"lt.{budget_filter}"),
            ("type", f"eq.{user_input.shoe_type.value}"),
            ("foot_shape", f"eq.{user_input.foot_shape.value}"),
            ("order", "price.asc"),
        ]

        if user_input.brand:
            query_params.append(("brand", f"ilike.*{user_input.brand}*"))

        encoded_query = parse.urlencode(query_params)
        return f"{self.base_url}/rest/v1/shoes?{encoded_query}"

    def _format_numeric_filter(self, value: float) -> str:
        logger.info("SupabaseShoeRepository._format_numeric_filter called value=%s", value)
        return str(int(value)) if float(value).is_integer() else str(value)

    def _fetch_rows(self, url: str) -> list[dict[str, Any]]:
        logger.info("SupabaseShoeRepository._fetch_rows called url=%s", url)
        req = request.Request(
            url,
            headers={
                "apikey": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.exception("SupabaseShoeRepository._fetch_rows http error: %s", detail)
            raise ValueError(
                f"Supabase request failed with status {exc.code}: {detail}"
            ) from exc
        except Exception as exc:
            logger.exception("SupabaseShoeRepository._fetch_rows failed: %s", exc)
            raise

        parsed_body = json.loads(raw_body)
        if not isinstance(parsed_body, list):
            raise ValueError("Supabase shoes query did not return a JSON array")
        return [row for row in parsed_body if isinstance(row, dict)]

    def _row_to_recommendation(
        self, row: dict[str, Any], user_input: RecommendationRequest
    ) -> RecommendationItem:
        logger.info("SupabaseShoeRepository._row_to_recommendation called")
        name = str(row.get("shoe_name") or row.get("name") or "").strip()
        brand = str(row.get("brand") or "").strip()
        if not name or not brand:
            raise ValueError(f"Supabase row missing required shoe fields: {row}")

        price = row.get("price")
        foot_shape = row.get("foot_shape")
        shoe_type = row.get("type")
        weight_grams = row.get("weight_grams")

        key_features: list[str] = []
        if price is not None:
            key_features.append(f"Price: S${price}")
        if shoe_type:
            key_features.append(f"Type: {shoe_type}")
        if foot_shape:
            key_features.append(f"Foot shape: {foot_shape}")
        if weight_grams is not None:
            key_features.append(f"Weight: {weight_grams}g")

        return RecommendationItem(
            name=name,
            brand=brand,
            score=100,
            price_sgd=float(price) if price is not None else None,
            weight_grams=int(weight_grams) if weight_grams is not None else None,
            key_features=key_features,
            reason=(
                "Matched your selected filters"
                f" for budget under S${user_input.budget:.0f},"
                f" shoe type {user_input.shoe_type.value},"
                f" and foot shape {user_input.foot_shape.value}."
            ),
            best_for=str(shoe_type or user_input.shoe_type.value),
            image_source=row.get("image_source"),
            sources=[],
        )
