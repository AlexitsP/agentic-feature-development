# kernel

The shared **feature-plugin kernel** (`type:kernel`) — the generic capabilities every feature
builds on (ADR-0008, ADR-0009, ADR-0010). It knows **nothing** about any specific feature.

## Modules

- `registry.py` — `FeatureManifest`, `ClaimSpec`; the builders the worker/poller consume
  (`build_workflows` / `build_activities` / `build_claims` / `build_routes`), `enabled_features`,
  and `apply_feature_flags` (env allowlist, ADR-0010).
- `confidence.py` — `score_confidence(ConfidenceSignals)` → a tiered badge from **observable**
  signals (ADR-0009). Pure.
- `sources.py` — `resolve_sources(urls, allowlist)` (drop off-list URLs, dedupe) and
  `grounding_ratio(cited, allowlist)`. Pure.

## Governing doc

- [`MANIFESTO.md`](./MANIFESTO.md) — the binding rules (what the kernel may and may not do,
  the public contract, forbidden imports). **Read before changing anything here.**

## Running unit tests

```bash
cd temporal && python -m pytest tests/test_registry.py tests/test_confidence.py tests/test_sources.py -v
```
