"""Azure OpenAI model client with Entra-first, API-key-fallback auth.

This is the model-wiring layer: it turns configuration (endpoint, deployment,
auth) into a ready-to-use client for the deployed Azure OpenAI model. Higher
layers (tools, workflows) build on `ModelClient.chat`.

Auth mode (`AZURE_OPENAI_AUTH`):
  - "entra": Microsoft Entra ID via DefaultAzureCredential only (keyless).
  - "key":   API key only.
  - "auto":  prefer Entra; on an auth failure, fall back to the API key if one
             is configured, and remember it for subsequent calls.

The deployed model here is a reasoning model (gpt-5-mini), so token budgets use
`max_completion_tokens` and temperature is left at the service default.
"""
from __future__ import annotations

import logging
from typing import Any

from openai import AzureOpenAI, AuthenticationError, PermissionDeniedError

from ..config import settings

logger = logging.getLogger(__name__)

# Entra token scope for the Azure Cognitive Services / OpenAI data plane.
_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"

# Entra-side failures that should trigger the API-key fallback in "auto" mode:
# both "authenticated but forbidden" and "no usable credential available".
try:  # azure-identity is optional for key-only deployments.
    from azure.core.exceptions import ClientAuthenticationError
    from azure.identity import CredentialUnavailableError

    _ENTRA_ERRORS: tuple[type[Exception], ...] = (
        ClientAuthenticationError,
        CredentialUnavailableError,
    )
except Exception:  # pragma: no cover - azure-identity not installed
    _ENTRA_ERRORS = ()

_AUTH_FALLBACK_ERRORS = (AuthenticationError, PermissionDeniedError, *_ENTRA_ERRORS)


class ModelConfigError(RuntimeError):
    """Raised when the client lacks the minimum configuration to run."""


def _entra_token_provider():
    # Imported lazily so a key-only deployment need not resolve azure-identity.
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    return get_bearer_token_provider(DefaultAzureCredential(), _COGNITIVE_SCOPE)


class ModelClient:
    """Thin wrapper over the Azure OpenAI SDK with resilient auth."""

    def __init__(self) -> None:
        if not settings.azure_openai_endpoint:
            raise ModelConfigError("AZURE_OPENAI_ENDPOINT is not set")
        if not settings.azure_openai_deployment:
            raise ModelConfigError("AZURE_OPENAI_DEPLOYMENT is not set")

        self._endpoint = settings.azure_openai_endpoint
        self._deployment = settings.azure_openai_deployment
        self._api_version = settings.azure_openai_api_version
        self._api_key = settings.azure_openai_api_key or None
        self._mode = (settings.azure_openai_auth or "auto").lower()
        self._active_auth = "key" if self._initial_auth() == "key" else "entra"
        self._client = self._build_client(self._active_auth)

    def _initial_auth(self) -> str:
        if self._mode == "key":
            if not self._api_key:
                raise ModelConfigError(
                    "AZURE_OPENAI_AUTH=key but AZURE_OPENAI_API_KEY is empty"
                )
            return "key"
        # "entra" and "auto" both start on Entra.
        return "entra"

    def _build_client(self, auth: str) -> AzureOpenAI:
        self._active_auth = auth
        if auth == "key":
            logger.info(
                "model client auth=key endpoint=%s deployment=%s",
                self._endpoint,
                self._deployment,
            )
            return AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_version=self._api_version,
                api_key=self._api_key,
            )
        logger.info(
            "model client auth=entra endpoint=%s deployment=%s",
            self._endpoint,
            self._deployment,
        )
        return AzureOpenAI(
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
            azure_ad_token_provider=_entra_token_provider(),
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_completion_tokens: int = 1024,
        **kwargs: Any,
    ):
        """One chat completion. Returns the raw Azure OpenAI response object.

        In "auto" mode, an Entra auth failure transparently retries with the
        configured API key (once), so the same code path works whether or not
        the caller's identity holds the "Cognitive Services OpenAI User" role.
        """
        try:
            return self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                **kwargs,
            )
        except _AUTH_FALLBACK_ERRORS as exc:
            if self._mode == "auto" and self._active_auth == "entra" and self._api_key:
                logger.warning(
                    "Entra auth failed (%s); falling back to API key",
                    exc.__class__.__name__,
                )
                self._client = self._build_client("key")
                return self._client.chat.completions.create(
                    model=self._deployment,
                    messages=messages,
                    max_completion_tokens=max_completion_tokens,
                    **kwargs,
                )
            raise

    @property
    def active_auth(self) -> str:
        """Which auth mode is currently in effect ("entra" or "key")."""
        return self._active_auth
