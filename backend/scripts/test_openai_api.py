from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = ROOT_DIR / "backend" / ".env"
OPENAI_URL = "https://api.openai.com/v1/responses"


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


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    started_at = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.status
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "duration_ms": round((time.time() - started_at) * 1000, 1),
            "error": detail,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "duration_ms": round((time.time() - started_at) * 1000, 1),
            "error": str(exc),
        }

    try:
        parsed_body: Any = json.loads(response_body)
    except json.JSONDecodeError:
        parsed_body = response_body

    return {
        "ok": 200 <= status_code < 300,
        "status_code": status_code,
        "duration_ms": round((time.time() - started_at) * 1000, 1),
        "response": parsed_body,
    }


def call_openai(model: str, timeout: int) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}

    payload = {
        "model": model,
        "input": 'Reply with valid JSON only: {"service":"openai","status":"ok"}',
        "text": {"format": {"type": "json_object"}},
    }
    result = post_json(
        OPENAI_URL,
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )

    if result.get("ok"):
        response = result.get("response", {})
        result["response_id"] = response.get("id")
        result["output_text"] = response.get("output_text")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test direct OpenAI API calls."
    )
    parser.add_argument(
        "--openai-model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    )
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    load_env_file(BACKEND_ENV_FILE)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env_file_loaded": str(BACKEND_ENV_FILE),
        "openai": call_openai(args.openai_model, args.timeout),
    }

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
