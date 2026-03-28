from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urljoin

from dotenv import load_dotenv

ALLOWED_BRANDS = {"adidas", "nike", "puma", "asics", "hoka", "saucony"}
ALLOWED_TYPES = ["daily trainer", "racer", "long run", "trail", "tempo"]
ALLOWED_FOOT_SHAPES = {"wide", "neutral", "narrow"}

DEFAULT_BRAND_URLS = {
    "adidas": "https://www.adidas.com.sg/",
    "nike": "https://www.nike.com/sg/",
    "puma": "https://sg.puma.com/sg/en/home",
    "asics": "https://www.asics.com/sg/en-sg/",
    "hoka": "https://www.hoka.com/en/us/",
    "saucony": "https://www.saucony.com/en/home",
}

TYPE_KEYWORDS = {
    "daily trainer": ["daily", "everyday", "trainer", "easy run", "jog"],
    "racer": ["racer", "race", "marathon", "competition", "carbon"],
    "long run": ["long run", "endurance", "ultra", "distance"],
    "trail": ["trail", "off-road", "all terrain", "grip", "mud"],
    "tempo": ["tempo", "speed", "interval", "threshold", "fartlek"],
}

LOGGER = logging.getLogger("scrape_brand_catalog_to_supabase")
NUMERIC_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = ROOT_DIR / "backend" / ".env"
DEFAULT_OUTPUT_PATH = str(ROOT_DIR / "backend" / "logs" / "shoe_catalog.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape adidas/nike/puma/asics/hoka/saucony catalogs with TinyFish, "
            "normalize to a strict shoe JSON schema, and upsert into Supabase."
        )
    )
    parser.add_argument(
        "--brands",
        nargs="+",
        choices=sorted(ALLOWED_BRANDS),
        default=sorted(ALLOWED_BRANDS),
        help="Brands to scrape.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Max concurrent TinyFish scraping requests.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="HTTP timeout in seconds for each upstream request.",
    )
    parser.add_argument(
        "--sgd-per-usd",
        type=float,
        default=1.35,
        help="FX rate for converting USD prices to SGD when needed.",
    )
    parser.add_argument(
        "--max-items-per-brand",
        type=int,
        default=0,
        help="Optional cap per brand after normalization (0 means no cap).",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help="JSON output file path.",
    )
    parser.add_argument(
        "--tinyfish-base-url",
        default=os.getenv(
            "TINYFISH_BASE_URL", "https://agent.tinyfish.ai/v1/automation/run"
        ),
        help="TinyFish automation endpoint.",
    )
    parser.add_argument(
        "--log-tinyfish-progress",
        action="store_true",
        help="Stream and log TinyFish progress events via /run-sse.",
    )
    parser.add_argument(
        "--supabase-table",
        default="shoes",
        help="Supabase table name for upsert.",
    )
    parser.add_argument(
        "--supabase-batch-size",
        type=int,
        default=200,
        help="Number of rows per upsert batch to Supabase.",
    )
    parser.add_argument(
        "--upload-to-supabase",
        action="store_true",
        help="Enable Supabase upsert. Disabled by default.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any brand fails scraping.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_environment() -> None:
    load_dotenv(BACKEND_ENV_FILE)
    load_dotenv()


def build_goal(brand: str, maxShoes: int) -> str:
    return (
        f"You are crawling {brand} running shoes catalog pages in Singapore and must capture {maxShoes == 0 and 'all' or maxShoes} unique running shoe models. "
        "Traverse listing/pagination pages and product detail pages reachable from the start URL. "
        "Return strict JSON only with this shape: "
        '{"shoes":[{"name":"","price":"","brand":"","weight":"",'
        '"type":[],"description":"","image_source":"","url":"","foot_shape":""}]} '
        "Rules: include each model once, include SGD price when available, include weight in grams when available, "
        "and only use these type values when known: daily trainer, racer, long run, trail, tempo."
    )


def post_json(
    url: str,
    payload: Any,
    headers: dict[str, str],
    timeout: int,
    require_json_object: bool = True,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.status
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"URL error calling {url}: {exc.reason}") from exc

    if not response_body.strip():
        return {"status_code": status_code}

    parsed: Any
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        if require_json_object:
            raise RuntimeError(
                f"Non-JSON response (status {status_code}) from {url}"
            ) from exc
        return {"status_code": status_code, "raw": response_body}

    if require_json_object and not isinstance(parsed, dict):
        raise RuntimeError(
            f"Unexpected JSON payload type from {url}: {type(parsed).__name__}"
        )

    if isinstance(parsed, dict):
        parsed.setdefault("status_code", status_code)
        return parsed
    return {"status_code": status_code, "data": parsed}


def tinyfish_sse_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/run-sse"):
        return normalized
    if normalized.endswith("/run"):
        return f"{normalized}-sse"
    return normalized


def _extract_tinyfish_run_payload(event_payload: Any) -> dict[str, Any] | None:
    if not isinstance(event_payload, dict):
        return None

    if any(key in event_payload for key in ("status", "result", "run_id")):
        return event_payload

    nested = event_payload.get("data")
    if isinstance(nested, dict) and any(
        key in nested for key in ("status", "result", "run_id")
    ):
        return nested

    return None


def _log_tinyfish_sse_event(brand: str, payload: Any) -> None:
    if isinstance(payload, dict):
        top_event = str(payload.get("event") or payload.get("type") or "").strip()
        top_status = str(payload.get("status") or "").strip()
        message = str(
            payload.get("message") or payload.get("detail") or payload.get("step") or ""
        ).strip()

        nested = payload.get("data") if isinstance(payload.get("data"), dict) else None
        nested_event = (
            str(nested.get("event") or nested.get("type") or "").strip()
            if nested
            else ""
        )
        nested_status = str(nested.get("status") or "").strip() if nested else ""

        event = top_event or nested_event or "update"
        status = top_status or nested_status or "n/a"
        if message:
            LOGGER.info(
                "tinyfish_progress brand=%s event=%s status=%s message=%s",
                brand,
                event,
                status,
                message,
            )
        else:
            LOGGER.info(
                "tinyfish_progress brand=%s event=%s status=%s",
                brand,
                event,
                status,
            )
        return

    LOGGER.info("tinyfish_progress brand=%s data=%s", brand, str(payload)[:200])


def post_sse_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    brand: str,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    final_payload: dict[str, Any] | None = None

    try:
        with request.urlopen(req, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue

                data_text = line[len("data:") :].strip()
                if not data_text or data_text == "[DONE]":
                    continue

                parsed = maybe_parse_json(data_text)
                _log_tinyfish_sse_event(brand, parsed)

                candidate = _extract_tinyfish_run_payload(parsed)
                if candidate is not None:
                    final_payload = candidate
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} calling {url}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"URL error calling {url}: {exc.reason}") from exc

    if final_payload is None:
        raise RuntimeError("TinyFish SSE stream ended without a final run payload")

    return final_payload


def maybe_parse_json(raw: Any) -> Any:
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return raw
    return raw


def collect_candidate_products(payload: Any) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    stack: list[Any] = [payload]

    while stack:
        current = stack.pop()
        current = maybe_parse_json(current)

        if isinstance(current, dict):
            if looks_like_product(current):
                products.append(current)
            for value in current.values():
                if isinstance(value, (dict, list, str)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(current)

    return products


def looks_like_product(item: dict[str, Any]) -> bool:
    name_like_keys = {"name", "shoe_name", "model", "title", "product_name"}
    has_name = any(k in item and item.get(k) for k in name_like_keys)
    if not has_name:
        return False

    useful_keys = {
        "price",
        "price_sgd",
        "price_usd",
        "weight",
        "weight_grams",
        "description",
        "image",
        "image_source",
        "url",
        "product_url",
        "link",
        "href",
    }
    return any(k in item for k in useful_keys)


def normalize_brand(value: Any, fallback_brand: str) -> str:
    text = str(value or "").strip().lower()
    if text in ALLOWED_BRANDS:
        return text
    return fallback_brand


def first_non_empty(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = NUMERIC_RE.search(value.replace(" ", ""))
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def normalize_price_sgd(item: dict[str, Any], sgd_per_usd: float) -> int | None:
    direct_sgd = first_non_empty(item, ["price_sgd"])
    if direct_sgd is not None:
        number = parse_number(direct_sgd)
        if number is not None:
            return int(round(number))

    usd_value = first_non_empty(item, ["price_usd", "msrp_usd"])
    if usd_value is not None:
        number = parse_number(usd_value)
        if number is not None:
            return int(round(number * sgd_per_usd))

    generic_price = first_non_empty(item, ["price", "list_price", "msrp"])
    if generic_price is None:
        return None

    number = parse_number(generic_price)
    if number is None:
        return None

    as_text = str(generic_price).lower()
    currency = str(item.get("currency") or "").lower()
    is_usd = (
        "usd" in as_text or "usd" in currency or "$" in as_text and "sg" not in as_text
    )
    if is_usd:
        number *= sgd_per_usd

    return int(round(number))


def normalize_weight_grams(item: dict[str, Any]) -> int | None:
    weight_raw = first_non_empty(item, ["weight_grams", "weight", "shoe_weight"])
    if weight_raw is None:
        return None

    if isinstance(weight_raw, (int, float)):
        return int(round(float(weight_raw)))

    text = str(weight_raw).strip().lower()
    number = parse_number(text)
    if number is None:
        return None

    if "oz" in text:
        number *= 28.3495

    return int(round(number))


def normalize_description(item: dict[str, Any]) -> str:
    value = first_non_empty(
        item, ["description", "summary", "details", "long_description"]
    )
    if value is None:
        return ""
    return str(value).strip()


def normalize_image_source(item: dict[str, Any]) -> str:
    value = first_non_empty(item, ["image_source", "image_url", "image", "thumbnail"])
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str):
            return first.strip()
    if isinstance(value, dict):
        maybe_url = first_non_empty(value, ["url", "src", "href"])
        if isinstance(maybe_url, str):
            return maybe_url.strip()
    return ""


def normalize_shoe_url(item: dict[str, Any], fallback_brand: str) -> str:
    value = first_non_empty(
        item,
        [
            "url",
            "product_url",
            "product_link",
            "href",
            "link",
            "pdp_url",
            "productPageUrl",
        ],
    )

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return ""
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
        return urljoin(DEFAULT_BRAND_URLS[fallback_brand], candidate)

    if isinstance(value, dict):
        nested = first_non_empty(value, ["url", "href", "src"])
        if isinstance(nested, str):
            candidate = nested.strip()
            if not candidate:
                return ""
            if candidate.startswith("http://") or candidate.startswith("https://"):
                return candidate
            return urljoin(DEFAULT_BRAND_URLS[fallback_brand], candidate)

    return ""


def tokenize_text(text: str) -> list[str]:
    return re.split(r"[^a-z0-9]+", text.lower())


def normalize_types(item: dict[str, Any], name: str, description: str) -> list[str]:
    result: list[str] = []

    explicit = first_non_empty(item, ["type", "types", "category", "use_case", "usage"])
    explicit_values: list[str] = []
    if isinstance(explicit, str):
        explicit_values = [explicit]
    elif isinstance(explicit, list):
        explicit_values = [str(v) for v in explicit if str(v).strip()]

    for raw in explicit_values:
        lowered = raw.strip().lower()
        for canonical, keywords in TYPE_KEYWORDS.items():
            if lowered == canonical or any(keyword in lowered for keyword in keywords):
                if canonical not in result:
                    result.append(canonical)

    searchable_text = f"{name} {description}".lower()
    for canonical, keywords in TYPE_KEYWORDS.items():
        if canonical in result:
            continue
        if any(keyword in searchable_text for keyword in keywords):
            result.append(canonical)

    if not result:
        result = ["daily trainer"]

    return [shoe_type for shoe_type in result if shoe_type in ALLOWED_TYPES]


def normalize_foot_shape(item: dict[str, Any], name: str, description: str) -> str:
    explicit = (
        str(first_non_empty(item, ["foot_shape", "fit", "last"]) or "").strip().lower()
    )
    for candidate in ALLOWED_FOOT_SHAPES:
        if candidate in explicit:
            return candidate

    searchable = f"{name} {description}".lower()
    if "wide" in searchable:
        return "wide"
    if "narrow" in searchable or "slim" in searchable:
        return "narrow"
    return "neutral"


def normalize_row(
    item: dict[str, Any], fallback_brand: str, sgd_per_usd: float
) -> dict[str, Any] | None:
    name = str(
        first_non_empty(item, ["name", "shoe_name", "model", "title", "product_name"])
        or ""
    ).strip()
    if not name:
        return None

    brand = normalize_brand(item.get("brand"), fallback_brand)
    if brand not in ALLOWED_BRANDS:
        return None

    description = normalize_description(item)
    normalized = {
        "name": name,
        "price": normalize_price_sgd(item, sgd_per_usd),
        "brand": brand,
        "weight": normalize_weight_grams(item),
        "type": normalize_types(item, name, description),
        "description": description,
        "image_source": normalize_image_source(item),
        "url": normalize_shoe_url(item, fallback_brand=brand),
        "foot_shape": normalize_foot_shape(item, name, description),
    }

    if not normalized["type"]:
        normalized["type"] = ["daily trainer"]

    return normalized


def row_richness_score(row: dict[str, Any]) -> int:
    score = 0
    if row.get("price") is not None:
        score += 1
    if row.get("weight") is not None:
        score += 1
    if row.get("description"):
        score += 1
    if row.get("image_source"):
        score += 1
    if row.get("url"):
        score += 1
    if row.get("foot_shape") and row.get("foot_shape") != "neutral":
        score += 1
    score += len(row.get("type") or [])
    return score


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (row["brand"], row["name"].strip().lower())
        current = keyed.get(key)
        if current is None:
            keyed[key] = row
            continue
        if row_richness_score(row) > row_richness_score(current):
            keyed[key] = row

    return sorted(keyed.values(), key=lambda x: (x["brand"], x["name"].lower()))


def _coerce_db_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _coerce_db_type(value: Any) -> str:
    candidates: list[str] = []
    if isinstance(value, str):
        candidates = [value.strip().lower()]
    elif isinstance(value, list):
        candidates = [str(v).strip().lower() for v in value if str(v).strip()]

    for candidate in candidates:
        if candidate in ALLOWED_TYPES:
            return candidate
        for canonical, keywords in TYPE_KEYWORDS.items():
            if candidate == canonical or any(
                keyword in candidate for keyword in keywords
            ):
                return canonical

    return "daily trainer"


def _coerce_db_foot_shape(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in ALLOWED_FOOT_SHAPES:
        return text
    if "wide" in text:
        return "wide"
    if "narrow" in text or "slim" in text:
        return "narrow"
    return "neutral"


def prepare_rows_for_shoes_schema(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    prepared: list[dict[str, Any]] = []
    dropped = 0

    for row in rows:
        name = str(row.get("name") or "").strip()
        brand = str(row.get("brand") or "").strip().lower()

        if not name or brand not in ALLOWED_BRANDS:
            dropped += 1
            continue

        prepared.append(
            {
                "name": name,
                "price": _coerce_db_int(row.get("price")),
                "brand": brand,
                "weight": _coerce_db_int(row.get("weight")),
                "type": _coerce_db_type(row.get("type")),
                "description": str(row.get("description") or "").strip(),
                "image_source": str(row.get("image_source") or "").strip(),
                "foot_shape": _coerce_db_foot_shape(row.get("foot_shape")),
                # Keep this explicit to satisfy schemas without DB defaults.
                "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    return prepared, dropped


async def scrape_one_brand(
    brand: str,
    url: str,
    tinyfish_base_url: str,
    tinyfish_api_key: str,
    log_tinyfish_progress: bool,
    timeout: int,
    sgd_per_usd: float,
    semaphore: asyncio.Semaphore,
    max_items_per_brand: int,
) -> tuple[str, list[dict[str, Any]], str | None]:
    payload = {
        "url": url,
        "goal": build_goal(brand, max_items_per_brand),
        "browser_profile": "lite",
        "api_integration": "tinyfish-brand-catalog-sync",
    }

    headers = {"X-API-Key": tinyfish_api_key}

    async with semaphore:
        try:
            if log_tinyfish_progress:
                response = await asyncio.to_thread(
                    post_sse_json,
                    tinyfish_sse_url(tinyfish_base_url),
                    payload,
                    headers,
                    timeout,
                    brand,
                )
            else:
                response = await asyncio.to_thread(
                    post_json,
                    tinyfish_base_url,
                    payload,
                    headers,
                    timeout,
                )
        except Exception as exc:  # noqa: BLE001
            return brand, [], str(exc)

    status = str(response.get("status") or "")
    if status and status.upper() != "COMPLETED":
        return brand, [], f"TinyFish status={status} error={response.get('error')}"

    result_payload = maybe_parse_json(response.get("result"))
    candidates = collect_candidate_products(result_payload)

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized = normalize_row(
            candidate, fallback_brand=brand, sgd_per_usd=sgd_per_usd
        )
        if normalized is None:
            continue
        rows.append(normalized)

    deduped = dedupe_rows(rows)
    if max_items_per_brand > 0:
        deduped = deduped[:max_items_per_brand]

    LOGGER.info(
        "brand=%s url=%s raw_candidates=%d normalized=%d",
        brand,
        url,
        len(candidates),
        len(deduped),
    )
    return brand, deduped, None


async def scrape_all_brands(
    brands: list[str],
    tinyfish_base_url: str,
    tinyfish_api_key: str,
    log_tinyfish_progress: bool,
    timeout: int,
    concurrency: int,
    sgd_per_usd: float,
    max_items_per_brand: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    tasks = [
        scrape_one_brand(
            brand=brand,
            url=DEFAULT_BRAND_URLS[brand],
            tinyfish_base_url=tinyfish_base_url,
            tinyfish_api_key=tinyfish_api_key,
            log_tinyfish_progress=log_tinyfish_progress,
            timeout=timeout,
            sgd_per_usd=sgd_per_usd,
            semaphore=semaphore,
            max_items_per_brand=max_items_per_brand,
        )
        for brand in brands
    ]

    results = await asyncio.gather(*tasks)

    combined: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for brand, rows, err in results:
        if err:
            errors[brand] = err
            LOGGER.error("brand=%s scrape_failed=%s", brand, err)
            continue
        combined.extend(rows)

    return dedupe_rows(combined), errors


def chunked(items: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        return [items]
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def upsert_supabase(
    rows: list[dict[str, Any]],
    supabase_url: str,
    supabase_service_role_key: str,
    table: str,
    timeout: int,
    batch_size: int,
) -> None:
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{table}?on_conflict=brand,name"
    headers = {
        "apikey": supabase_service_role_key,
        "Authorization": f"Bearer {supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    prepared_rows, dropped_rows = prepare_rows_for_shoes_schema(rows)
    if dropped_rows:
        LOGGER.warning("dropped_rows_for_schema_validation count=%d", dropped_rows)
    if not prepared_rows:
        LOGGER.warning("no_rows_left_after_schema_validation")
        return

    for index, batch in enumerate(chunked(prepared_rows, batch_size), start=1):
        LOGGER.info("upsert_batch=%d rows=%d endpoint=%s", index, len(batch), endpoint)
        _ = post_json(
            endpoint,
            payload=batch,
            headers=headers,
            timeout=timeout,
            require_json_object=False,
        )


def ensure_required_env(
    upload_to_supabase: bool,
) -> tuple[str, str | None, str | None]:
    tinyfish_api_key = os.getenv("TINYFISH_API_KEY")
    if not tinyfish_api_key:
        raise ValueError("Missing TINYFISH_API_KEY")

    if not upload_to_supabase:
        return tinyfish_api_key, None, None

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_service_role_key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    return tinyfish_api_key, supabase_url, supabase_service_role_key


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    load_environment()

    try:
        tinyfish_api_key, supabase_url, supabase_service_role_key = ensure_required_env(
            args.upload_to_supabase
        )
    except ValueError as exc:
        LOGGER.error(str(exc))
        return 2

    max_items_per_brand = args.max_items_per_brand

    rows, scrape_errors = asyncio.run(
        scrape_all_brands(
            brands=args.brands,
            tinyfish_base_url=args.tinyfish_base_url,
            tinyfish_api_key=tinyfish_api_key,
            log_tinyfish_progress=args.log_tinyfish_progress,
            timeout=args.timeout,
            concurrency=args.concurrency,
            sgd_per_usd=args.sgd_per_usd,
            max_items_per_brand=max_items_per_brand,
        )
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    LOGGER.info("wrote_json_output path=%s rows=%d", output_path, len(rows))

    if args.upload_to_supabase and rows:
        assert supabase_url is not None
        assert supabase_service_role_key is not None
        upsert_supabase(
            rows=rows,
            supabase_url=supabase_url,
            supabase_service_role_key=supabase_service_role_key,
            table=args.supabase_table,
            timeout=args.timeout,
            batch_size=args.supabase_batch_size,
        )
        LOGGER.info(
            "supabase_upsert_complete rows=%d table=%s", len(rows), args.supabase_table
        )

    if args.strict and scrape_errors:
        LOGGER.error("strict_mode_failure scrape_errors=%s", scrape_errors)
        return 1

    json.dump(rows, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if scrape_errors:
        LOGGER.warning("completed_with_errors scrape_errors=%s", scrape_errors)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
