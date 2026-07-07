"""Activities for the Gains Check workflow: fetch a GIF and finalize the row."""
from __future__ import annotations

import base64
import datetime as dt
from typing import Any
from xml.sax.saxutils import escape

import httpx
from temporalio import activity

from ..agents.tools import gains_tools
from ..config import settings

_SPEECH_VOICE = "en-US-DavisNeural"


def _rest_base() -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _write_headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@activity.defn
def search_gif(query: str) -> dict[str, Any]:
    return gains_tools.search_gif(query)


@activity.defn
def synthesize_speech(text: str, hype: bool) -> str | None:
    """Neural TTS via Azure Speech. Returns base64 MP3, or None if unconfigured/failed."""
    key = settings.azure_speech_key
    region = settings.azure_speech_region
    if not key or not region or not text:
        return None
    style = "excited" if hype else "angry"
    pitch = "+12%" if hype else "-6%"
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>"
        f"<voice name='{_SPEECH_VOICE}'>"
        f"<mstts:express-as style='{style}' styledegree='2'>"
        f"<prosody rate='+8%' pitch='{pitch}' volume='+80%'>{escape(text)}</prosody>"
        "</mstts:express-as></voice></speak>"
    )
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                    "User-Agent": "gainscheck",
                },
                content=ssml.encode("utf-8"),
            )
            if resp.status_code != 200:
                return None
            return base64.b64encode(resp.content).decode("ascii")
    except Exception:
        return None


@activity.defn
def record_gains_event(
    check_id: str, seq: int, stage: str, label: str, detail: Any = None, tokens: int | None = None
) -> None:
    """Append a pipeline trace event for the frontend stepper."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_rest_base()}/gains_events",
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "check_id": check_id,
                "seq": seq,
                "stage": stage,
                "label": label,
                "detail": detail,
                "tokens": tokens,
            },
        )
        resp.raise_for_status()


@activity.defn
def finalize_gains(check_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    with httpx.Client(timeout=15.0) as client:
        resp = client.patch(
            f"{_rest_base()}/gains_checks",
            params={"id": f"eq.{check_id}"},
            headers={**_write_headers(), "Prefer": "return=minimal"},
            json={
                "status": status,
                "result": result,
                "error": error,
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
        )
        resp.raise_for_status()
