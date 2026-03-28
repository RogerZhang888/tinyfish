from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.models.schemas import RecommendationRequest
from backend.services.shoe_repository import SupabaseShoeRepository


BACKEND_ENV_FILE = ROOT_DIR / "backend" / ".env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Supabase shoes table queries."
    )
    parser.add_argument("--budget", type=float, default=170)
    parser.add_argument("--brand", default="")
    parser.add_argument("--shoe-type", default="daily trainer")
    parser.add_argument("--foot-shape", default="neutral")
    parser.add_argument("--running-style", default="midfoot")
    parser.add_argument("--height-cm", type=float, default=175)
    parser.add_argument("--weight-kg", type=float, default=70)
    parser.add_argument("--weekly-mileage-km", type=float, default=40)
    parser.add_argument("--experience-level", default="intermediate")
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args()

    load_env_file(BACKEND_ENV_FILE)

    request_payload = RecommendationRequest(
        budget=args.budget,
        brand=args.brand or None,
        shoe_type=args.shoe_type,
        foot_shape=args.foot_shape,
        running_style=args.running_style,
        preferences=[],
        height_cm=args.height_cm,
        weight_kg=args.weight_kg,
        weekly_mileage_km=args.weekly_mileage_km,
        experience_level=args.experience_level,
        max_results=args.max_results,
    )

    started_at = time.time()
    repository = SupabaseShoeRepository()

    try:
        recommendations = repository.search_shoes(request_payload)
        output = {
            "ok": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "env_file_loaded": str(BACKEND_ENV_FILE),
            "table": "shoes",
            "filters": {
                "budget_lt": args.budget,
                "brand": args.brand or None,
                "shoe_type": args.shoe_type,
                "foot_shape": args.foot_shape,
            },
            "duration_ms": round((time.time() - started_at) * 1000, 1),
            "count": len(recommendations),
            "recommendations": [
                recommendation.model_dump(mode="json")
                for recommendation in recommendations
            ],
        }
    except Exception as exc:
        output = {
            "ok": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "env_file_loaded": str(BACKEND_ENV_FILE),
            "table": "shoes",
            "filters": {
                "budget_lt": args.budget,
                "brand": args.brand or None,
                "shoe_type": args.shoe_type,
                "foot_shape": args.foot_shape,
            },
            "duration_ms": round((time.time() - started_at) * 1000, 1),
            "error": str(exc),
        }

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
