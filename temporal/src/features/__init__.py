"""Feature plug-ins for the education-advisor platform (ADR-0008).

Each subpackage is a self-contained feature declaring a `FeatureManifest`
(see `<feature>/manifest.py`). Features depend on `src.kernel`, never on each
other. The worker/poller/frontend build their registration, claim, and route
lists by iterating the enabled feature manifests.

NOTE: this package `__init__` is kept import-light on purpose. Feature workflows
live under this package, and Temporal's workflow sandbox re-imports the package on
registration — eager imports here (e.g. the registry, which pulls in httpx/openai
activities) would trip the sandbox. Import the registry explicitly from
`src.features.registry` instead.
"""
