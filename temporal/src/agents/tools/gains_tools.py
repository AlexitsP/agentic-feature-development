"""Tools for the Gains Check app: coach personas + the verdict/plan tool schemas."""
from __future__ import annotations

from typing import Any


# Coach personalities. The user picks one; it sets the tone of the evaluation.
PERSONAS: dict[str, dict[str, str]] = {
    "gymbro": {
        "label": "Gym Bro",
        "voice": "a loud, funny hype gym bro (think Ronnie Coleman / Arnold) who SCREAMS encouragement",
    },
    "sergeant": {
        "label": "Drill Sergeant",
        "voice": "a brutal military drill sergeant who barks short, clipped orders and accepts NO excuses",
    },
    "wholesome": {
        "label": "Wholesome Coach",
        "voice": "a kind, endlessly supportive coach who is genuinely proud of any effort and is never mean, only gently encouraging",
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
                    "assessment": {"type": "string", "description": "A genuine 2-4 sentence evaluation of their tracked numbers: what's solid, what's lacking, and where they stand. Specific and useful — your coach voice is fine, but the substance must be real."},
                    "suggested_goal": {"type": "string", "enum": ["recomp", "weight_loss", "build_muscle", "get_lean"], "description": "The single goal that best fits their numbers right now."},
                    "suggestion_reason": {"type": "string", "description": "1-2 sentences: why that goal fits them, grounded in their numbers."},
                },
                "required": ["passed", "assessment", "suggested_goal", "suggestion_reason"],
            },
        },
    },
]


# Agentic mode uses the same serious verdict tool; the difference is the prompt
# (free reasoning, no fixed formula) and that the tool choice is not forced.
AGENTIC_TOOLS: list[dict[str, Any]] = TOOLS


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
