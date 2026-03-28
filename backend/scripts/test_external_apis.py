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
TINYFISH_URL = "https://agent.tinyfish.ai/v1/automation/run"


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


def call_gemini(model: str, timeout: int) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured"}

    base_url = os.getenv(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    url = f"{base_url}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            'Reply with valid JSON only: '
                            '{"service":"google_ai_studio","status":"ok"}'
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }
    result = post_json(
        url,
        payload,
        headers={},
        timeout=timeout,
    )

    if result.get("ok"):
        response = result.get("response", {})
        candidates = response.get("candidates", [])
        result["model_version"] = response.get("modelVersion")
        result["output_text"] = _extract_gemini_text(candidates)
    return result


def _extract_gemini_text(candidates: object) -> str | None:
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        text_parts = []
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        if text_parts:
            return "\n".join(text_parts)
    return None


def call_tinyfish(target_url: str, goal: str, timeout: int) -> dict[str, Any]:
    api_key = os.getenv("TINYFISH_API_KEY")
    if not api_key:
        return {"ok": False, "error": "TINYFISH_API_KEY is not configured"}

    payload = {
        "url": target_url,
        "goal": (
            f"{goal} Return strict JSON only with shape "
            '{"page_title":"","summary":"","links":[{"text":"","href":""}]}'
        ),
        "browser_profile": "lite",
        "proxy_config": {"enabled": True, "country_code": "US"},
        "api_integration": "runwise-smoke-test",
    }
    result = post_json(
        TINYFISH_URL,
        payload,
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )

    if result.get("ok"):
        response = result.get("response", {})
        result["run_id"] = response.get("run_id")
        result["run_status"] = response.get("status")
        result["result_preview"] = response.get("result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test direct Google AI Studio and TinyFish API calls."
    )
    parser.add_argument("--gemini-model", default=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    parser.add_argument("--tinyfish-url", default="https://runrepeat.com/")
    parser.add_argument(
        "--tinyfish-goal",
        default="Find the page title and a short summary of what this site offers.",
    )
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    load_env_file(BACKEND_ENV_FILE)

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env_file_loaded": str(BACKEND_ENV_FILE),
        "google_ai_studio": call_gemini(args.gemini_model, args.timeout),
        "tinyfish": call_tinyfish(args.tinyfish_url, args.tinyfish_goal, args.timeout),
    }

    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
