"""Tools for the Gains Check demo: fetch a GIF on the fly + the verdict schema."""
from __future__ import annotations

import random
from typing import Any

import httpx

from ...config import settings

_GIPHY_SEARCH = "https://api.giphy.com/v1/gifs/search"


def search_gif(query: str, rating: str = "pg-13") -> dict[str, Any]:
    """Fetch a GIF URL for a query via Giphy (if GIPHY_API_KEY is set).

    Returns {url, source, query}. Without a key, url is None and the frontend
    falls back to an emoji — the demo still runs.
    """
    key = settings.giphy_api_key
    if not key:
        return {"url": None, "source": "no-key", "query": query}
    try:
        resp = httpx.get(
            _GIPHY_SEARCH,
            params={"api_key": key, "q": query, "limit": 15, "rating": rating, "bundle": "messaging_non_clips"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or []
        if not data:
            return {"url": None, "source": "empty", "query": query}
        gif = random.choice(data)
        images = gif.get("images", {})
        url = (
            images.get("downsized_medium", {}).get("url")
            or images.get("downsized", {}).get("url")
            or images.get("original", {}).get("url")
        )
        return {"url": url, "source": "giphy", "query": query}
    except Exception as exc:  # never let a GIF hiccup break the verdict
        return {"url": None, "source": f"error:{type(exc).__name__}", "query": query}


# OpenAI tool schemas. The agent fetches a GIF, then submits its verdict.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_gif",
            "description": "Fetch a GIF URL for a search query (e.g. 'Ronnie Coleman yeah buddy', 'angry dog barking').",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Return the final verdict. Call exactly once, after fetching a GIF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean", "description": "true if they are tracking and doing it right"},
                    "headline": {"type": "string", "description": "Big on-screen text, e.g. 'YEAH BUDDY!' or 'YOU SHOULD'"},
                    "spoken_line": {"type": "string", "description": "What the browser voice shouts, e.g. a Ronnie Coleman catchphrase, or a scolding"},
                    "gif_url": {"type": "string", "description": "The url returned by search_gif (empty string if none)"},
                    "sound": {"type": "string", "enum": ["hype", "shame"]},
                    "reason": {"type": "string", "description": "One-line why, coach voice"},
                },
                "required": ["passed", "headline", "spoken_line", "sound", "reason"],
            },
        },
    },
]
