"""Program Evaluator: counselor personas, the curated Swiss source allowlist, the
`submit_evaluation` tool schema, and the pure result builder.

The result builder is where the kernel is used: links are constrained to the source
allowlist (`resolve_sources`) and the confidence badge is computed from observable
signals (`score_confidence`) — never from anything the model says about its own
certainty.
"""
from __future__ import annotations

from typing import Any

from ...kernel.confidence import ConfidenceSignals, score_confidence
from ...kernel.sources import grounding_ratio, resolve_sources

# Institution types (Swiss higher-ed): University / University of Applied Sciences
# (Fachhochschule) / University of Teacher Education (PH).
INSTITUTION_TYPES = ("university", "uas", "ph")

# Professional counselor tones (the student picks one). No comedy — this is real advice.
PERSONAS: dict[str, dict[str, str]] = {
    "mentor": {
        "label": "Encouraging Mentor",
        "voice": "a warm, encouraging study advisor who leads with the student's strengths "
        "and frames options positively while staying honest about fit",
    },
    "advisor": {
        "label": "Straight-talking Advisor",
        "voice": "a pragmatic, plain-spoken advisor who is direct about fit, entry requirements, "
        "and trade-offs",
    },
    "analyst": {
        "label": "Detailed Analyst",
        "voice": "a thorough, analytical advisor who explains the reasoning and compares options "
        "carefully",
    },
}


def get_persona(key: str | None) -> dict[str, str]:
    return PERSONAS.get((key or "").lower(), PERSONAS["mentor"])


# Curated, official Swiss higher-education sources. The model may cite ONLY these; any
# other URL is dropped by `resolve_sources`, so links shown to a student are always real.
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
    """The allowlist, formatted for the system prompt (URL — title)."""
    return "\n".join(f"- {s['url']} — {s['title']}" for s in SOURCES)


# Expected profile fields, used to measure how much the student told us.
_EXPECTED_FIELDS = ("interests", "prior_qualification", "strong_subjects", "target_field", "canton", "language")


def _present(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return True


def compute_input_completeness(user_input: dict) -> float:
    """0..1 — how complete the student's profile is. Free text counts as moderate signal."""
    provided = sum(1 for k in _EXPECTED_FIELDS if _present(user_input.get(k)))
    ratio = provided / len(_EXPECTED_FIELDS)
    if _present(user_input.get("freeform")):
        return max(0.5, ratio)
    return ratio


# The model returns its evaluation through this tool. Forced (called exactly once).
SUBMIT_EVALUATION_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "submit_evaluation",
            "description": "Return the study-fit evaluation. Call exactly once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assessment": {
                        "type": "string",
                        "description": "2-4 sentence plain-language read of the student's fit and readiness for higher education, grounded in what they provided.",
                    },
                    "suggested_options": {
                        "type": "array",
                        "description": "1-3 concrete study options that fit the student.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "description": "Field of study, e.g. 'Medicine', 'Computer Science'."},
                                "institution_type": {"type": "string", "enum": list(INSTITUTION_TYPES), "description": "university | uas (Fachhochschule) | ph (teacher education)"},
                                "reason": {"type": "string", "description": "Why this fits, grounded in the student's profile."},
                            },
                            "required": ["field", "institution_type", "reason"],
                        },
                    },
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "1-4 URLs chosen ONLY from the provided official source list.",
                    },
                    "out_of_scope": {
                        "type": "boolean",
                        "description": "true if the request is not about choosing a higher-education study option.",
                    },
                },
                "required": ["assessment", "suggested_options", "source_urls"],
            },
        },
    },
]


def build_evaluation_result(args: dict, persona_label: str, user_input: dict) -> dict:
    """Coerce the model's tool args into the result contract + attach a confidence badge.

    Pure and deterministic: safe defaults for missing fields, institution types constrained
    to the enum, links constrained to the allowlist, confidence from observable signals.
    """
    options: list[dict] = []
    for o in (args.get("suggested_options") or [])[:3]:
        it = o.get("institution_type")
        if it not in INSTITUTION_TYPES:
            it = "university"
        options.append({"field": o.get("field") or "", "institution_type": it, "reason": o.get("reason") or ""})

    source_urls = args.get("source_urls") or []
    resources = resolve_sources(source_urls, SOURCES)

    conf = score_confidence(
        ConfidenceSignals(
            input_completeness=compute_input_completeness(user_input),
            grounding=grounding_ratio(source_urls, SOURCES),
            source_count=len(resources),
            out_of_scope=bool(args.get("out_of_scope")),
        )
    )

    return {
        "assessment": args.get("assessment") or "",
        "suggested_options": options,
        "resources": resources,
        "persona": persona_label,
        "confidence": {"tier": conf.tier, "badge": conf.badge, "score": conf.score, "reasons": conf.reasons},
    }
