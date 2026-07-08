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
                },
                "required": ["passed", "headline", "spoken_line", "sound", "reason"],
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
                "Call it as many times as you like to find a GIF that fits your verdict."
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
                },
                "required": ["passed", "headline", "spoken_line", "reason", "gif_url", "voice_style"],
            },
        },
    },
]


# ── Gains Plan ────────────────────────────────────────────────────────────────
# Curated, verified-stable resource links the plan agent hands out. The model may
# only pick from THIS list (URLs resolved against it) so links are never invented.
PLAN_RESOURCES: list[dict[str, Any]] = [
    {"title": "r/Fitness Wiki — beginner's guide to training & nutrition", "url": "https://thefitness.wiki/", "tags": ["general", "beginner", "training", "nutrition"]},
    {"title": "Examine.com — evidence-based nutrition & supplements", "url": "https://examine.com/", "tags": ["nutrition", "general"]},
    {"title": "Stronger by Science — deeply researched training & nutrition", "url": "https://www.strongerbyscience.com/", "tags": ["training", "nutrition", "science", "muscle"]},
    {"title": "StrongLifts 5x5 — simple beginner strength program", "url": "https://stronglifts.com/5x5/", "tags": ["training", "muscle", "beginner", "strength"]},
    {"title": "Renaissance Periodization — hypertrophy & diet guides", "url": "https://rpstrength.com/", "tags": ["muscle", "fatloss", "recomp", "training"]},
    {"title": "Academy of Nutrition & Dietetics (eatright.org)", "url": "https://www.eatright.org/", "tags": ["nutrition", "health", "weightloss"]},
    {"title": "ACSM — physical activity guidelines", "url": "https://www.acsm.org/", "tags": ["general", "health"]},
    {"title": "Muscle & Strength — free workout routines", "url": "https://www.muscleandstrength.com/workout-routines", "tags": ["training", "muscle", "beginner"]},
    {"title": "Healthline — how to count macros", "url": "https://www.healthline.com/nutrition/how-to-count-macros", "tags": ["nutrition", "beginner", "weightloss", "recomp"]},
]


def plan_resources_prompt() -> str:
    """The resource list, formatted for the plan prompt (URL — title [tags])."""
    return "\n".join(f"- {r['url']} — {r['title']} [{', '.join(r['tags'])}]" for r in PLAN_RESOURCES)


def resolve_plan_resources(urls: list[str]) -> list[dict[str, str]]:
    """Map model-chosen URLs to {title,url}, keeping ONLY known ones (no invented links)."""
    by_url = {r["url"]: {"title": r["title"], "url": r["url"]} for r in PLAN_RESOURCES}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for u in urls or []:
        r = by_url.get((u or "").strip())
        if r and r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return out


# submit_plan tool — the plan agent returns a concise starter plan. Forced (guided-style)
# for reliability; resource_urls are constrained to PLAN_RESOURCES by the workflow.
PLAN_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Return a concise, actionable starter plan for the user's goal. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "2-3 sentences: the approach for their goal given their stats and verdict"},
                    "calorie_guidance": {"type": "string", "description": "A concrete calorie target/direction, e.g. 'eat ~2600 kcal/day (small deficit)'"},
                    "protein_guidance": {"type": "string", "description": "A concrete protein target, e.g. 'hit ~150 g protein/day'"},
                    "training_focus": {"type": "string", "description": "One line on the training emphasis for this goal"},
                    "weekly_steps": {"type": "array", "items": {"type": "string"}, "description": "4-6 concrete actions to start this week"},
                    "resource_urls": {"type": "array", "items": {"type": "string"}, "description": "2-4 URLs chosen ONLY from the provided resource list"},
                },
                "required": ["summary", "weekly_steps", "resource_urls"],
            },
        },
    },
]


# submit_advice tool — each specialist agent on the plan panel returns its slice.
ADVISOR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_advice",
            "description": "Return your specialist advice for the plan panel. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string", "description": "One line summarizing your recommendation"},
                    "points": {"type": "array", "items": {"type": "string"}, "description": "2-4 concrete, evidence-based pointers in your area"},
                    "calorie_guidance": {"type": "string", "description": "Calorie target/direction if nutrition is your area; else empty string"},
                    "protein_guidance": {"type": "string", "description": "Protein target if nutrition is your area; else empty string"},
                    "training_focus": {"type": "string", "description": "Training emphasis if training is your area; else empty string"},
                },
                "required": ["headline", "points"],
            },
        },
    },
]
