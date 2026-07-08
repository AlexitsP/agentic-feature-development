"""Gains Check feature — the original demo, expressed as a plug-in manifest.

The workflow/activity code still lives in `src/workflows` and `src/activities`; this
package only declares the manifest so the existing flows register through the same
feature registry as new features (ADR-0008). A later refactor may physically relocate
the code here.
"""
