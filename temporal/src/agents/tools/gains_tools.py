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


# OpenAI tool schema. The model only decides the verdict; the workflow fetches
# the themed GIF deterministically afterwards (guaranteed Ronnie/Arnold on a pass).
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Return the final verdict. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean", "description": "true if they are tracking and doing it right"},
                    "headline": {"type": "string", "description": "Big on-screen text, e.g. 'YEAH BUDDY!' or 'YOU SHOULD'"},
                    "spoken_line": {"type": "string", "description": "What the voice shouts — a Ronnie Coleman / Arnold catchphrase on a pass, or a scolding on a fail"},
                    "sound": {"type": "string", "enum": ["hype", "shame"]},
                    "reason": {"type": "string", "description": "One-line why, coach voice"},
                },
                "required": ["passed", "headline", "spoken_line", "sound", "reason"],
            },
        },
    },
]

# Themed GIF search terms. Pass = bodybuilding legends; fail = doghouse.
HYPE_QUERIES = [
    "Ronnie Coleman yeah buddy",
    "Ronnie Coleman lightweight",
    "Arnold Schwarzenegger flexing",
    "Arnold Schwarzenegger pump",
]
SHAME_QUERIES = ["angry dog barking", "disappointed dog", "sad dog"]
