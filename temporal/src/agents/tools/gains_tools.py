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
                    "legend_quip": {"type": "string", "description": "A funny 1-2 sentence comparison of the user's numbers to the named legend's numbers"},
                },
                "required": ["passed", "headline", "spoken_line", "sound", "reason", "legend_quip"],
            },
        },
    },
]

# Pass-verdict subjects. The GIF and the on-screen/spoken line come from the
# SAME person, so the meme quote always matches the GIF that's shown.
HYPE_SUBJECTS = {
    "Ronnie Coleman": {
        "queries": ["Ronnie Coleman yeah buddy", "Ronnie Coleman lightweight", "Ronnie Coleman deadlift"],
        "quotes": [
            "YEAH BUDDY!",
            "LIGHTWEIGHT, BABY!",
            "AIN'T NOTHIN' BUT A PEANUT!",
            "EVERYBODY WANNA BE A BODYBUILDER, BUT DON'T NOBODY WANNA LIFT NO HEAVY-ASS WEIGHT!",
        ],
    },
    "Arnold Schwarzenegger": {
        "queries": ["Arnold Schwarzenegger flexing", "Arnold Schwarzenegger pump", "Arnold Schwarzenegger bodybuilding"],
        "quotes": [
            "I'LL BE BACK... FOR ANOTHER SET!",
            "GET TO DA CHOPPA... AND THEN THE SQUAT RACK!",
            "COME WITH ME IF YOU WANT TO LIFT!",
            "THE PUMP IS THE GREATEST FEELING!",
        ],
    },
}
SHAME_QUERIES = ["angry dog barking", "disappointed dog", "sad dog"]

# Legends to stack the user up against. Stats are approximate contest condition.
LEGENDS = [
    {"name": "Ronnie Coleman", "weight_kg": 137, "height_cm": 180, "body_fat_pct": 4,
     "gif_query": "Ronnie Coleman", "fun_fact": "8-time Mr. Olympia who squatted 800 lb yelling 'YEAH BUDDY'."},
    {"name": "Arnold Schwarzenegger", "weight_kg": 107, "height_cm": 188, "body_fat_pct": 5,
     "gif_query": "Arnold Schwarzenegger bodybuilding", "fun_fact": "7-time Mr. Olympia, then the Terminator, then a Governor."},
    {"name": "Dorian Yates", "weight_kg": 122, "height_cm": 178, "body_fat_pct": 4,
     "gif_query": "Dorian Yates", "fun_fact": "'The Shadow' — 6 Olympias on brutally heavy training."},
    {"name": "Jay Cutler", "weight_kg": 121, "height_cm": 175, "body_fat_pct": 5,
     "gif_query": "Jay Cutler bodybuilder", "fun_fact": "4-time Mr. Olympia who finally dethroned Ronnie."},
    {"name": "Phil Heath", "weight_kg": 113, "height_cm": 175, "body_fat_pct": 4,
     "gif_query": "Phil Heath", "fun_fact": "'The Gift' — 7 straight Mr. Olympia titles."},
    {"name": "Chris Bumstead", "weight_kg": 100, "height_cm": 185, "body_fat_pct": 4,
     "gif_query": "Chris Bumstead", "fun_fact": "'CBum' — the Classic Physique king."},
    {"name": "Frank Zane", "weight_kg": 85, "height_cm": 175, "body_fat_pct": 5,
     "gif_query": "Frank Zane", "fun_fact": "3-time Mr. Olympia and the icon of aesthetics."},
    {"name": "Iris Kyle", "weight_kg": 74, "height_cm": 168, "body_fat_pct": 6,
     "gif_query": "Iris Kyle bodybuilder", "fun_fact": "10-time Ms. Olympia — the most decorated bodybuilder, period."},
    {"name": "Dana Linn Bailey", "weight_kg": 63, "height_cm": 168, "body_fat_pct": 8,
     "gif_query": "Dana Linn Bailey", "fun_fact": "The first-ever Women's Physique Olympia champion."},
    {"name": "Andrea Shaw", "weight_kg": 77, "height_cm": 173, "body_fat_pct": 6,
     "gif_query": "Andrea Shaw bodybuilder", "fun_fact": "Multiple-time Ms. Olympia who brought back mass and symmetry."},
    {"name": "Cydney Gillon", "weight_kg": 60, "height_cm": 165, "body_fat_pct": 8,
     "gif_query": "Cydney Gillon", "fun_fact": "Dominant multi-time Figure Olympia champion."},
]
