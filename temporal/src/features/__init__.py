"""Feature plug-ins for the education-advisor platform (ADR-0008).

Each subpackage is a self-contained feature declaring a `FeatureManifest`
(see `<feature>/manifest.py`). Features depend on `src.kernel`, never on each
other. The worker/poller/frontend build their registration, claim, and route
lists by iterating the enabled feature manifests.
"""
