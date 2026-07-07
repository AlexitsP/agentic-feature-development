"""Connectivity smoke test for the Azure OpenAI model wiring.

Run from the temporal/ directory:

    python -m src.agents.check_connectivity

Exit codes: 0 = model replied, 1 = replied empty, 2 = misconfigured/unauthorized.
"""
from __future__ import annotations

import logging
import sys

from openai import AuthenticationError, PermissionDeniedError

from .model_client import ModelClient, ModelConfigError

logging.basicConfig(level=logging.INFO)


def main() -> int:
    try:
        client = ModelClient()
    except ModelConfigError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 2

    try:
        resp = client.chat(
            [{"role": "user", "content": "Reply with exactly the word: pong"}],
            max_completion_tokens=256,
        )
    except (AuthenticationError, PermissionDeniedError) as exc:
        print(f"AUTH ERROR ({client.active_auth}): {exc}")
        return 2

    choice = resp.choices[0]
    content = choice.message.content or ""
    print(
        f"OK auth={client.active_auth} model={resp.model} "
        f"finish={choice.finish_reason} content={content!r}"
    )
    return 0 if content.strip() else 1


if __name__ == "__main__":
    sys.exit(main())
