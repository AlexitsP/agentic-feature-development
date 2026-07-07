"""Read-only Supabase tools the model can call, plus their OpenAI schemas.

These read a single entity's data via PostgREST using the service role. They are
the ONLY source of truth the model is allowed to use for an insight.
"""
from __future__ import annotations

from typing import Any

import httpx

from ...config import settings

_TIMEOUT = 15.0


def _base() -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def get_entity(entity_id: str) -> dict[str, Any]:
    """Fetch an entity's type and current version data."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        ent_resp = client.get(
            f"{_base()}/entities",
            params={"id": f"eq.{entity_id}", "select": "id,entity_type,source_record_id"},
            headers=_headers(),
        )
        ent_resp.raise_for_status()
        entities = ent_resp.json()
        if not entities:
            return {"found": False, "entity_id": entity_id}

        ver_resp = client.get(
            f"{_base()}/entity_versions",
            params={
                "entity_id": f"eq.{entity_id}",
                "is_current": "eq.true",
                "select": "version_number,data,valid_from",
            },
            headers=_headers(),
        )
        ver_resp.raise_for_status()
        versions = ver_resp.json()

    entity = entities[0]
    return {
        "found": True,
        "entity_id": entity_id,
        "entity_type": entity.get("entity_type"),
        "source_record_id": entity.get("source_record_id"),
        "current_version": versions[0] if versions else None,
    }


def get_entity_facts(entity_id: str) -> list[dict[str, Any]]:
    """Fetch the entity's numeric facts with their labels and units."""
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            f"{_base()}/entity_facts",
            params={
                "entity_id": f"eq.{entity_id}",
                "select": "value,dimension_type,fact_types(key,label,unit)",
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()

    facts: list[dict[str, Any]] = []
    for row in rows or []:
        fact_type = row.get("fact_types") or {}
        facts.append(
            {
                "key": fact_type.get("key"),
                "label": fact_type.get("label"),
                "unit": fact_type.get("unit"),
                "value": row.get("value"),
            }
        )
    return facts


# OpenAI tool (function-calling) schemas. `submit_insight` is how the model
# returns its final, structured answer -- no free-text parsing needed.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_entity",
            "description": "Fetch an entity's type and current version data.",
            "parameters": {
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_facts",
            "description": "Fetch the entity's numeric facts (label, value, unit).",
            "parameters": {
                "type": "object",
                "properties": {"entity_id": {"type": "string"}},
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_insight",
            "description": (
                "Return the final structured insight. Call exactly once when done. "
                "Use only values returned by the other tools; do not invent data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Plain-language summary of the entity.",
                    },
                    "notable_facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                    "data_completeness": {
                        "type": "string",
                        "enum": ["full", "partial", "insufficient"],
                    },
                },
                "required": ["summary", "data_completeness"],
            },
        },
    },
]
