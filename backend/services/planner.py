from __future__ import annotations

from pathlib import Path

from backend.models.schemas import PlannedTarget, RecommendationRequest, ScrapePlan
from backend.services.openai_client import OpenAIClient


class QueryPlanner:
    """Step 1: Build a scrape plan from the curated websites catalog file."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        websites_file: Path | None = None,
    ) -> None:
        self.openai_client = openai_client
        self.websites_file = (
            websites_file or Path(__file__).resolve().parents[2] / "websites.md"
        )

    def create_plan(self, user_input: RecommendationRequest) -> ScrapePlan:
        domain_sections = self._read_website_sections()
        allowed_targets: list[PlannedTarget] = []

        for section, domains in domain_sections.items():
            for domain in domains:
                source_type = self._source_type_for(section, domain)
                allowed_targets.append(
                    PlannedTarget(
                        url=self._normalize_url(domain),
                        goal=self._goal_for(source_type, user_input),
                        source_type=source_type,
                    )
                )

        if not allowed_targets:
            raise ValueError(
                f"No valid websites found in {self.websites_file}. Add domains under markdown headers."
            )

        llm_targets = self.openai_client.plan_targets(user_input) or []
        if llm_targets:
            allowed_by_host = {
                target.url.host.removeprefix("www."): target for target in allowed_targets
            }
            filtered_targets: list[PlannedTarget] = []
            for target in llm_targets:
                allowed_target = allowed_by_host.get(
                    target.url.host.removeprefix("www.")
                )
                if not allowed_target:
                    continue
                filtered_targets.append(
                    PlannedTarget(
                        url=target.url,
                        goal=target.goal,
                        source_type=allowed_target.source_type,
                    )
                )
            if filtered_targets:
                return ScrapePlan(targets=filtered_targets)

        return ScrapePlan(targets=allowed_targets)

    def _read_website_sections(self) -> dict[str, list[str]]:
        if not self.websites_file.exists():
            raise ValueError(f"Website catalog file not found: {self.websites_file}")

        sections: dict[str, list[str]] = {}
        current_section = "general"
        sections[current_section] = []

        for raw_line in self.websites_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("##"):
                current_section = line.lstrip("#").strip().lower()
                sections.setdefault(current_section, [])
                continue
            sections.setdefault(current_section, []).append(line)

        return sections

    def _source_type_for(self, section: str, domain: str) -> str:
        section_lower = section.lower()
        domain_lower = domain.lower()

        if "reddit.com" in domain_lower:
            return "community"
        if "review" in section_lower:
            return "review_blog"
        if "shoe" in section_lower:
            return "brand_site"
        return "comparison_site"

    def _normalize_url(self, domain_or_url: str) -> str:
        value = domain_or_url.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return f"https://{value}"

    def _goal_for(self, source_type: str, user_input: RecommendationRequest) -> str:
        if source_type == "brand_site":
            return (
                f"Find {user_input.shoe_type.value} models around ${user_input.budget:.0f} and extract "
                "specs: cushioning, stability, shoe weight, fit notes, and list price"
            )
        if source_type == "review_blog":
            return (
                "Extract expert verdict, use-case fit, pros/cons, durability notes, and ride feel "
                "for relevant shoes"
            )
        if source_type == "community":
            return (
                "Extract community sentiment, long-term comfort feedback, fit issues, and recurring "
                "complaints"
            )
        return "Extract structured running shoe metadata and user-relevant tradeoffs"
