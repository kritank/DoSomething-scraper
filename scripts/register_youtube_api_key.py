from __future__ import annotations
"""
Register a YouTube Data API v3 key into the pool used by
YouTubeJobProcessor.

Unlike Instagram accounts, there's no login flow -- generate a key in a
Google Cloud project (APIs & Services > Credentials, with the "YouTube Data
API v3" enabled), then register it here. The script validates the key with
one live, cheap call (channels.list?forHandle=@youtube) before persisting it,
so a typo'd or unauthorized key fails immediately instead of silently
sitting in the pool until a real job hits it.

Usage:
    uv run python scripts/register_youtube_api_key.py --label gcp-project-1
    (prompts for the API key)
"""

import argparse
import asyncio
import getpass

import httpx

from app.core.database import get_session
from app.repositories.youtube_api_key_repo import YouTubeApiKeyRepo


async def _validate_key(api_key: str) -> tuple[bool, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id", "forHandle": "@youtube", "key": api_key},
            )
        except Exception as e:
            return False, f"Network error while validating key: {e}"

    if response.status_code == 200:
        return True, ""
    try:
        detail = response.json().get("error", {}).get("message", response.text)
    except Exception:
        detail = response.text
    return False, f"HTTP {response.status_code}: {detail}"


async def register(label: str, api_key: str) -> int:
    print(f"Validating key '{label}' against the YouTube Data API...")
    ok, detail = await _validate_key(api_key)
    if not ok:
        print(f"Validation failed: {detail}")
        return 1

    async with get_session() as session:
        await YouTubeApiKeyRepo(session).create(label=label, api_key=api_key)
    print(f"Registered YouTube API key '{label}' -- active and available to the scrape pool.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a YouTube Data API v3 key into the pool.")
    parser.add_argument("--label", required=True, help="Human-readable name, e.g. the GCP project name.")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Prefer omitting this and using the prompt -- avoids it landing in shell history.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or getpass.getpass("YouTube Data API v3 key: ").strip()
    if not api_key:
        raise SystemExit("No API key provided.")
    exit_code = asyncio.run(register(args.label, api_key))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
