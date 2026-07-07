from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    temporal_address: str = Field("temporal:7233", env="TEMPORAL_ADDRESS")
    temporal_namespace: str = Field("default", env="TEMPORAL_NAMESPACE")
    temporal_task_queue: str = Field("main", env="TEMPORAL_TASK_QUEUE")
    supabase_url: str = Field("http://host.docker.internal:55321", env="SUPABASE_URL")
    supabase_service_role_key: str = Field("dev-service-role-key", env="SUPABASE_SERVICE_ROLE_KEY")

    # Azure OpenAI (model wiring). Endpoint/deployment are not secrets.
    azure_openai_endpoint: str = Field("", env="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str = Field("", env="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field("2024-10-21", env="AZURE_OPENAI_API_VERSION")
    # Optional API-key fallback; Entra ID (DefaultAzureCredential) is preferred.
    azure_openai_api_key: str = Field("", env="AZURE_OPENAI_API_KEY")
    # auth mode: "auto" (Entra first, key fallback) | "entra" | "key"
    azure_openai_auth: str = Field("auto", env="AZURE_OPENAI_AUTH")

    # Giphy API key for the Gains Check demo (optional; falls back to curated GIFs).
    giphy_api_key: str = Field("", env="GIPHY_API_KEY")

    # Azure Speech (neural TTS) for the spoken verdict. Optional; falls back to
    # the browser's speechSynthesis when unset.
    azure_speech_key: str = Field("", env="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field("", env="AZURE_SPEECH_REGION")

    class Config:
        case_sensitive = False

settings = Settings()
