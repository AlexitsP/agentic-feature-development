"""Study Planner: the advisor panel, head-coach personas, curated Swiss source
allowlist, the submit_advice / submit_plan tool schemas, and the pure plan builder.

The builder uses the kernel to constrain links to the allowlist and to compute the
confidence badge from observable signals (ADR-0009) — never model self-report.
"""
from __future__ import annotations

from typing import Any

from ...kernel.confidence import ConfidenceSignals, score_confidence
from ...kernel.sources import grounding_ratio, resolve_sources

# Head-coach tone (same professional set as the evaluator; each feature owns its copy to
# stay decoupled — features never import each other, ADR-0008).
PERSONAS: dict[str, dict[str, str]] = {
    "mentor": {"label": "Encouraging Mentor", "voice": "a warm, encouraging study advisor"},
    "advisor": {"label": "Straight-talking Advisor", "voice": "a pragmatic, plain-spoken advisor"},
    "analyst": {"label": "Detailed Analyst", "voice": "a thorough, analytical advisor"},
}


def get_persona(key: str | None) -> dict[str, str]:
    return PERSONAS.get((key or "").lower(), PERSONAS["mentor"])


# The specialist panel dispatched in parallel.
ADVISORS: list[dict[str, str]] = [
    {
        "key": "curriculum",
        "title": "Curriculum & pathway advisor",
        "role": "a Swiss higher-education curriculum & pathway advisor",
        "brief": "Give the concrete study path toward this goal: what to prioritise to enter and "
        "succeed, key milestones, and 2-3 pointers. Ground it in the student's situation.",
    },
    {
        "key": "study_skills",
        "title": "Study-skills coach",
        "role": "a learning-science / study-skills coach",
        "brief": "Give 2-4 evidence-based HOW-TO-STUDY techniques (e.g. spaced practice, retrieval "
        "practice, planning) tailored to this goal and level. Be concrete and realistic.",
    },
]

# Curated official/reputable Swiss sources the panel may cite. Model-chosen links are
# resolved against this list, so an invented URL is dropped rather than shown to a student.
SOURCES: list[dict[str, Any]] = [
    {"title": "swissuniversities — Swiss higher education institutions", "url": "https://www.swissuniversities.ch/en"},
    {"title": "orientation.ch — official study & career guidance", "url": "https://www.orientation.ch/"},
    {"title": "berufsberatung.ch — Studien- & Berufsberatung", "url": "https://www.berufsberatung.ch/"},
    {"title": "SERI — State Secretariat for Education, Research and Innovation", "url": "https://www.sbfi.admin.ch/sbfi/en/home.html"},
    {"title": "ETH Zurich — study programmes", "url": "https://ethz.ch/en/studies.html"},
    {"title": "EPFL — study programmes", "url": "https://www.epfl.ch/education/"},
    {"title": "University of Zurich — degree programmes", "url": "https://www.uzh.ch/en/studies.html"},
]


def sources_prompt() -> str:
    return "\n".join(f"- {s['url']} — {s['title']}" for s in SOURCES)


_EXPECTED_FIELDS = ("target_field", "prior_qualification", "timeframe", "interests")


def _present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return True


def compute_input_completeness(user_input: dict) -> float:
    provided = sum(1 for k in _EXPECTED_FIELDS if _present(user_input.get(k)))
    ratio = provided / len(_EXPECTED_FIELDS)
    if _present(user_input.get("freeform")):
        return max(0.5, ratio)
    return ratio


# Each panel advisor returns its slice through this tool (forced, called once).
ADVISOR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_advice",
            "description": "Return your specialist advice for the plan panel. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string", "description": "One line summarising your recommendation."},
                    "points": {"type": "array", "items": {"type": "string"}, "description": "2-4 concrete, evidence-based pointers in your area."},
                },
                "required": ["headline", "points"],
            },
        },
    },
]

# The head advisor synthesises the panel into one plan (forced, called once).
PLAN_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Return one cohesive study plan for the goal. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "2-3 sentences: the approach for this goal and situation."},
                    "weekly_steps": {"type": "array", "items": {"type": "string"}, "description": "4-6 concrete actions to start with."},
                    "how_to_study": {"type": "array", "items": {"type": "string"}, "description": "2-4 evidence-based study-skills / how-to-study pointers."},
                    "resource_urls": {"type": "array", "items": {"type": "string"}, "description": "2-4 URLs chosen ONLY from the provided official source list."},
                },
                "required": ["summary", "weekly_steps", "how_to_study", "resource_urls"],
            },
        },
    },
]


def build_plan_result(synth_args: dict, panel: list[dict], persona_label: str, user_input: dict) -> dict:
    """Coerce the synthesis (and panel) into the plan contract + attach a confidence badge. Pure."""
    weekly = [str(s) for s in (synth_args.get("weekly_steps") or [])][:6]
    how_to_study = [str(s) for s in (synth_args.get("how_to_study") or [])][:4]
    source_urls = synth_args.get("resource_urls") or []
    resources = resolve_sources(source_urls, SOURCES)

    conf = score_confidence(
        ConfidenceSignals(
            input_completeness=compute_input_completeness(user_input),
            grounding=grounding_ratio(source_urls, SOURCES),
            source_count=len(resources),
        )
    )

    return {
        "summary": synth_args.get("summary") or "",
        "weekly_steps": weekly,
        "how_to_study": how_to_study,
        "resources": resources,
        "persona": persona_label,
        "panel": [{"title": p.get("title", ""), "headline": p.get("headline", ""), "points": p.get("points", [])} for p in panel],
        "confidence": {"tier": conf.tier, "badge": conf.badge, "score": conf.score, "reasons": conf.reasons},
    }
