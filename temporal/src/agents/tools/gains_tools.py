"""Tools for the Gains Check demo: fetch a GIF on the fly + the verdict schema."""
from __future__ import annotations

import random
from typing import Any

import httpx

from ...config import settings

_GIPHY_SEARCH = "https://api.giphy.com/v1/gifs/search"


def search_gif(query: str, rating: str = "pg-13", fallback_query: str | None = None) -> dict[str, Any]:
    """Fetch a GIF URL for a query via Giphy (if GIPHY_API_KEY is set).

    Returns {url, source, query}. If the specific query comes back empty and a
    broader ``fallback_query`` is given, retries once with it before giving up.
    Without a key (or on any error) url is None; callers layer a curated
    fallback on top so a themed GIF always shows.
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
        if not data and fallback_query:
            # Broaden the search once before falling back to a curated GIF.
            return search_gif(fallback_query, rating=rating)
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


# Curated, verified-stable Giphy CDN URLs. Last-resort fallback so the verdict
# ALWAYS shows a themed GIF even if the live search is empty/errored/keyless.
FALLBACK_GIFS: dict[str, list[str]] = {
    "Ronnie Coleman": [
        "https://media.giphy.com/media/oJjl0sBWtX5ylDRGNF/giphy.gif",
        "https://media.giphy.com/media/h24Y1pZIGKXzG/giphy.gif",
        "https://media.giphy.com/media/zpeH9hHFP457a/giphy.gif",
    ],
    "Arnold Schwarzenegger": [
        "https://media.giphy.com/media/BCIoXfA95d1ba/giphy.gif",
        "https://media.giphy.com/media/wMaXHNDlucW35ZCC5n/giphy.gif",
        "https://media.giphy.com/media/9DnMb3eR7YRK0L6tYX/giphy.gif",
    ],
    "not_tracking": [
        "https://media.giphy.com/media/JJI0vSkEVNHXVMGV0c/giphy.gif",
        "https://media.giphy.com/media/5jI8q0Tg6tgeA/giphy.gif",
        "https://media.giphy.com/media/3oGRFIjETeuYgyLyo0/giphy.gif",
    ],
    "slacking": [
        "https://media.giphy.com/media/qdqxysIbFi6zHijLjp/giphy.gif",
        "https://media.giphy.com/media/7o5XoOYT3oXICXlgmj/giphy.gif",
        "https://media.giphy.com/media/CgjAoG5TiBbcOjDbXV/giphy.gif",
    ],
}


def fallback_gif_url(bucket: str) -> str | None:
    """A curated CDN GIF for a bucket (a HYPE subject name, or a fail kind)."""
    urls = FALLBACK_GIFS.get(bucket)
    return random.choice(urls) if urls else None


# Coach personalities. The user picks one; it steers the system-prompt voice and
# the neural-TTS speaking style (voice must support these mstts express-as styles).
PERSONAS: dict[str, dict[str, str]] = {
    "gymbro": {
        "label": "Gym Bro",
        "voice": "a loud, funny hype gym bro (think Ronnie Coleman / Arnold) who SCREAMS encouragement",
        "hype_style": "excited",
        "shame_style": "angry",
    },
    "sergeant": {
        "label": "Drill Sergeant",
        "voice": "a brutal military drill sergeant who barks short, clipped orders and accepts NO excuses",
        "hype_style": "shouting",
        "shame_style": "angry",
    },
    "wholesome": {
        "label": "Wholesome Coach",
        "voice": "a kind, endlessly supportive coach who is genuinely proud of any effort and is never mean, only gently encouraging",
        "hype_style": "cheerful",
        "shame_style": "hopeful",
    },
}


def get_persona(key: str | None) -> dict[str, str]:
    return PERSONAS.get((key or "").lower(), PERSONAS["gymbro"])


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
                    "fail_kind": {
                        "type": "string",
                        "enum": ["not_tracking", "slacking"],
                        "description": "Only when passed is false: 'not_tracking' if calories or protein are missing/zero (they aren't even logging); 'slacking' if they ARE tracking real numbers but the numbers are weak.",
                    },
                    "headline": {"type": "string", "description": "Big on-screen text, e.g. 'YEAH BUDDY!', 'YOU SHOULD', or 'DO BETTER'"},
                    "spoken_line": {"type": "string", "description": "What the voice shouts — a Ronnie Coleman / Arnold catchphrase on a pass, or a scolding on a fail"},
                    "sound": {"type": "string", "enum": ["hype", "shame"]},
                    "reason": {"type": "string", "description": "One-line why, in your coach voice"},
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

# Fail GIFs by kind. not_tracking = you aren't even logging (angry dog);
# slacking = you're logging but the numbers are weak (disappointed "come on").
SHAME_QUERIES: dict[str, list[str]] = {
    "not_tracking": ["angry dog barking", "disappointed dog", "sad dog"],
    "slacking": ["disappointed come on", "you can do better", "try harder gym"],
}


def shame_query(fail_kind: str | None) -> str:
    return random.choice(SHAME_QUERIES.get(fail_kind or "not_tracking", SHAME_QUERIES["not_tracking"]))


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


# Distance scales for legend matching. Deliberately NOT the legend spread: every
# legend is sub-8% contest-shredded, so normalising body fat by its tiny 4-8%
# range would let it dominate and collapse everyone onto the leanest-but-heaviest
# legend regardless of weight. These are realistic human gaps — a 35 kg weight
# gap counts about as "far" as a 12-point body-fat gap — so weight stays meaningful.
_WEIGHT_SCALE = 35.0
_BF_SCALE = 12.0


def legend_by_name(name: str | None) -> dict[str, Any] | None:
    """Look a legend up by (fuzzy) name — reference data for the agentic path,
    where the MODEL chooses which legend to compare against."""
    if not name:
        return None
    n = name.strip().lower()
    for l in LEGENDS:
        ln = l["name"].lower()
        if n == ln or n in ln or ln in n:
            return l
    return None


def legend_roster_text() -> str:
    """Compact roster the agentic model is given so it can pick a rival itself."""
    return "; ".join(
        f"{l['name']} ({l['weight_kg']}kg, {l['body_fat_pct']}% BF, {l['height_cm']}cm)" for l in LEGENDS
    )


# Neural-TTS express-as styles en-US-DavisNeural supports. In the agentic path
# the MODEL chooses the emotional delivery from this set.
VOICE_STYLES = ["excited", "shouting", "cheerful", "friendly", "angry", "hopeful", "sad"]


# ── Agentic tool set ─────────────────────────────────────────────────────────
# Unlike the guided TOOLS (a single forced submit_verdict), here the model gets a
# REAL tool it chooses when/how to use, and submit_verdict is NOT forced — so the
# model runs a genuine multi-step loop: reason -> search GIFs it picks -> decide.
AGENTIC_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_gif",
            "description": (
                "Search Giphy for a GIF and get a URL back. YOU choose the search terms. "
                "Call it as many times as you like — e.g. one GIF that fits your verdict, "
                "and one of the legend you compare against."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search terms, e.g. 'Ronnie Coleman yeah buddy' or 'sad dog'"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Return your final verdict. Call exactly once, after you've searched for any GIFs you want.",
            "parameters": {
                "type": "object",
                "properties": {
                    "passed": {"type": "boolean", "description": "true if, in your judgment, they're tracking and doing it right"},
                    "fail_kind": {
                        "type": "string",
                        "enum": ["not_tracking", "slacking"],
                        "description": "Only when passed is false: 'not_tracking' if they aren't logging calories/protein; 'slacking' if they log but the numbers are weak.",
                    },
                    "headline": {"type": "string", "description": "Big on-screen text in your voice"},
                    "spoken_line": {"type": "string", "description": "What the voice should shout/say"},
                    "reason": {"type": "string", "description": "One-line why, in character"},
                    "gif_url": {"type": "string", "description": "A URL you got back from search_gif that fits the verdict. Empty string if none suitable."},
                    "voice_style": {"type": "string", "enum": VOICE_STYLES, "description": "How the line should be spoken"},
                    "legend_name": {"type": "string", "description": "The legend you chose to compare the user against"},
                    "legend_comparison": {"type": "string", "description": "A funny comparison of the user's numbers to that legend's"},
                    "legend_gif_url": {"type": "string", "description": "A URL from search_gif of that legend, or empty string"},
                },
                "required": ["passed", "headline", "spoken_line", "reason", "gif_url", "voice_style", "legend_name", "legend_comparison"],
            },
        },
    },
]


def pick_closest_legend(user_input: dict[str, Any] | None) -> dict[str, Any]:
    """Pick the legend whose contest stats are nearest the user's numbers.

    Distance blends weight and body-fat gaps on realistic human scales (see
    above) so weight isn't drowned out. If the user gave neither weight nor body
    fat, there's nothing to match on, so pick at random. Returns a copy with
    ``matched`` set.
    """
    user_input = user_input or {}
    weight = user_input.get("weight_kg")
    bf = user_input.get("body_fat_pct")

    if weight is None and bf is None:
        legend = dict(random.choice(LEGENDS))
        legend["matched"] = False
        return legend

    def distance(l: dict[str, Any]) -> float:
        d = 0.0
        if weight is not None:
            d += (abs(l["weight_kg"] - weight) / _WEIGHT_SCALE) ** 2
        if bf is not None:
            d += (abs(l["body_fat_pct"] - bf) / _BF_SCALE) ** 2
        return d

    legend = dict(min(LEGENDS, key=distance))
    legend["matched"] = True
    return legend
