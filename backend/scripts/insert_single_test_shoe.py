from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = ROOT_DIR / "backend" / ".env"

ALLOWED_BRANDS = ["adidas", "nike", "puma", "asics", "hoka", "saucony"]
ALLOWED_TYPES = ["daily trainer", "racer", "long run", "trail", "tempo"]
ALLOWED_FOOT_SHAPES = ["wide", "neutral", "narrow"]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Insert one test shoe row into Supabase shoes table."
    )
    parser.add_argument(
        "--name",
        default=f"TinyFish Test Shoe {int(time.time())}",
        help="Shoe name for the test row.",
    )
    parser.add_argument("--price", type=int, default=199)
    parser.add_argument("--brand", choices=ALLOWED_BRANDS, default="nike")
    parser.add_argument("--weight", type=int, default=260)
    parser.add_argument("--type", choices=ALLOWED_TYPES, default="daily trainer")
    parser.add_argument(
        "--description",
        default="Inserted by insert_single_test_shoe.py",
    )
    parser.add_argument(
        "--image-source",
        default="https://example.com/test-shoe.jpg",
    )
    parser.add_argument(
        "--foot-shape",
        choices=ALLOWED_FOOT_SHAPES,
        default="neutral",
    )
    parser.add_argument(
        "--table",
        default="shoes",
        help="Supabase table to insert into.",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Use upsert with on_conflict=brand,name instead of plain insert.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds.",
    )
    return parser.parse_args()


def resolve_supabase_config() -> tuple[str, str]:
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    api_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_API_KEY", "").strip()
    )

    if not supabase_url:
        raise ValueError("SUPABASE_URL is not configured")
    if not api_key:
        raise ValueError(
            "SUPABASE_SERVICE_ROLE_KEY or SUPABASE_API_KEY is not configured"
        )

    return supabase_url.rstrip("/"), api_key


def make_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "name": args.name,
        "price": args.price,
        "brand": args.brand,
        "weight": args.weight,
        "type": args.type,
        "description": args.description,
        "image_source": args.image_source,
        "foot_shape": args.foot_shape,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


def parse_postgrest_error_code(detail: str) -> str | None:
    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, dict):
        code = parsed.get("code")
        if isinstance(code, str):
            return code
    return None


def post_row(
    supabase_url: str,
    api_key: str,
    table: str,
    payload: dict[str, object],
    timeout: int,
    upsert: bool,
) -> list[dict[str, object]]:
    endpoint = f"{supabase_url}/rest/v1/{table}"
    if upsert:
        endpoint = f"{endpoint}?on_conflict=brand,name"

    prefer = (
        "resolution=merge-duplicates,return=representation"
        if upsert
        else "return=representation"
    )

    req = request.Request(
        endpoint,
        data=json.dumps([payload]).encode("utf-8"),
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Prefer": prefer,
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        error_code = parse_postgrest_error_code(detail)
        if upsert and error_code == "42P10":
            raise RuntimeError(
                "Upsert failed because there is no unique constraint for on_conflict=brand,name. "
                "Run without --upsert for a one-off insert, or add this SQL first: "
                "ALTER TABLE public.shoes ADD CONSTRAINT shoes_brand_name_key UNIQUE (brand, name);"
            ) from exc
        raise RuntimeError(
            f"Supabase insert failed with status {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Supabase request failed: {exc.reason}") from exc

    if not raw_body.strip():
        return []

    parsed = json.loads(raw_body)
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    return []


def main() -> int:
    args = parse_args()
    load_env_file(BACKEND_ENV_FILE)

    try:
        supabase_url, api_key = resolve_supabase_config()
        payload = make_payload(args)
        inserted = post_row(
            supabase_url=supabase_url,
            api_key=api_key,
            table=args.table,
            payload=payload,
            timeout=args.timeout,
            upsert=args.upsert,
        )
    except Exception as exc:  # noqa: BLE001
        output = {
            "ok": False,
            "error": str(exc),
            "env_file_loaded": str(BACKEND_ENV_FILE),
        }
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    output = {
        "ok": True,
        "table": args.table,
        "mode": "upsert" if args.upsert else "insert",
        "payload": payload,
        "inserted_rows": inserted,
        "inserted_count": len(inserted),
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
