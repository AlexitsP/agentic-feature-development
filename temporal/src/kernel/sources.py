"""Kernel: curated source-allowlist resolution + grounding measure (ADR-0009).

A feature declares a curated
allowlist of official sources, and the model may only surface links from it — an
invented or off-list URL is dropped rather than shown to a student. The same
allowlist is used to measure `grounding` for the confidence score.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def resolve_sources(
    urls: Iterable[str] | None, allowlist: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Keep only URLs present in the allowlist, de-duplicated, first-seen order preserved."""
    by_url = {s["url"]: {"title": s["title"], "url": s["url"]} for s in allowlist}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for u in urls or []:
        r = by_url.get((u or "").strip())
        if r and r["url"] not in seen:
            seen.add(r["url"])
            out.append(r)
    return out


def grounding_ratio(
    cited_urls: Iterable[str] | None, allowlist: list[dict[str, Any]]
) -> float:
    """Share of cited URLs that resolve to an allowlisted source (0..1).

    An empty citation list scores 0.0 — nothing was grounded.
    """
    cited = list(cited_urls or [])
    if not cited:
        return 0.0
    known = {s["url"] for s in allowlist}
    hits = sum(1 for u in cited if (u or "").strip() in known)
    return hits / len(cited)
