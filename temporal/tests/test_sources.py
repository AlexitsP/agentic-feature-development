"""Kernel source-allowlist resolution + grounding measure (ADR-0009)."""
from src.kernel.sources import grounding_ratio, resolve_sources

ALLOW = [
    {"title": "swissuniversities", "url": "https://swissuniversities.ch/"},
    {"title": "orientation.ch", "url": "https://www.orientation.ch/"},
]


def test_invented_urls_dropped():
    out = resolve_sources(["https://evil.example/x", "https://swissuniversities.ch/"], ALLOW)
    assert out == [{"title": "swissuniversities", "url": "https://swissuniversities.ch/"}]


def test_dedup_preserves_first_order():
    out = resolve_sources(
        [
            "https://www.orientation.ch/",
            "https://swissuniversities.ch/",
            "https://www.orientation.ch/",
        ],
        ALLOW,
    )
    assert [r["url"] for r in out] == [
        "https://www.orientation.ch/",
        "https://swissuniversities.ch/",
    ]


def test_whitespace_trimmed():
    out = resolve_sources(["  https://swissuniversities.ch/  "], ALLOW)
    assert len(out) == 1


def test_empty_or_none_input():
    assert resolve_sources(None, ALLOW) == []
    assert resolve_sources([], ALLOW) == []


def test_grounding_ratio():
    assert grounding_ratio(["https://swissuniversities.ch/", "https://evil.example/"], ALLOW) == 0.5
    assert grounding_ratio(["https://swissuniversities.ch/"], ALLOW) == 1.0


def test_grounding_ratio_empty_is_zero():
    assert grounding_ratio([], ALLOW) == 0.0
    assert grounding_ratio(None, ALLOW) == 0.0
