"""Read-only Google Voices adapter and offline fixture adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any, Protocol


def field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


@dataclass(frozen=True)
class VoiceMetadata:
    provider_voice_id: str
    voice_type: str
    display_name: str | None = None
    model: str | None = None
    prompted_input: str | None = None
    description: str | None = None
    language_code: str | None = None
    region_code: str | None = None
    accent: str | None = None
    gender: str | None = None
    persona: str | None = None
    context: str | None = None
    pitch: str | None = None
    expire_time: str | None = None


@dataclass(frozen=True)
class VoicePage:
    voices: tuple[VoiceMetadata, ...]
    next_page_token: str | None


class ReadOnlyVoiceProvider(Protocol):
    def list_page(self, page_token: str | None, page_size: int) -> VoicePage: ...
    def get_voice(self, voice_id: str) -> VoiceMetadata: ...


def normalize_voice(value: Any) -> VoiceMetadata | None:
    voice_type = field(value, "type")
    if hasattr(voice_type, "value"):
        voice_type = voice_type.value
    if voice_type == "prebuilt":
        return None
    voice_id = field(value, "id")
    if voice_type not in {"prompted", "replicated"} or not isinstance(voice_id, str) or not voice_id.startswith("voice_"):
        raise ValueError("Malformed custom voice in provider response")
    prompted = field(value, "prompted")
    pitch = field(value, "pitch")
    if hasattr(pitch, "value"):
        pitch = pitch.value
    expiry = field(value, "expire_time")
    if isinstance(expiry, datetime):
        expiry = expiry.isoformat()
    if expiry is not None and not isinstance(expiry, str):
        raise ValueError("Malformed voice expiry in provider response")
    return VoiceMetadata(
        provider_voice_id=voice_id, voice_type=voice_type,
        display_name=field(value, "display_name"), model=field(value, "model"),
        prompted_input=field(prompted, "input"), description=field(value, "description"),
        language_code=field(value, "language_code"), region_code=field(value, "region_code"),
        accent=field(value, "accent"), gender=field(value, "gender"),
        persona=field(value, "persona"), context=field(value, "context"),
        pitch=pitch, expire_time=expiry,
    )


class GoogleVoicesAdapter:
    """Only exposes GET/list operations; owns and closes its SDK client."""

    def __init__(self, credential_env: str):
        key = os.environ.get(credential_env)
        if not key:
            raise ValueError("Configured Google credential environment variable is empty")
        try:
            from google import genai
        except ModuleNotFoundError as exc:
            raise ValueError(
                "Live sync requires google-genai==2.31.0 in the active Python environment"
            ) from exc
        self._client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})

    def __enter__(self) -> GoogleVoicesAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def list_page(self, page_token: str | None, page_size: int) -> VoicePage:
        response = self._client.voices.list(
            type_=["prompted", "replicated"], page_size=page_size, page_token=page_token,
        )
        voices = tuple(v for raw in (response.voices or ()) if (v := normalize_voice(raw)) is not None)
        return VoicePage(voices, response.next_page_token or None)

    def get_voice(self, voice_id: str) -> VoiceMetadata:
        voice = normalize_voice(self._client.voices.get(id=voice_id))
        if voice is None or voice.provider_voice_id != voice_id:
            raise ValueError("Provider returned an unexpected voice")
        return voice


class FixtureVoicesAdapter:
    """Simulate paginated list/get calls entirely from a JSON fixture."""

    def __init__(self, fixture: dict[str, Any]):
        pages = fixture.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("Fixture requires at least one page")
        self._pages: dict[str | None, VoicePage] = {}
        expected_token: str | None = None
        for index, raw_page in enumerate(pages):
            if expected_token in self._pages or not isinstance(raw_page, dict):
                raise ValueError("Fixture has a repeated page token or malformed page")
            raw_voices = raw_page.get("voices")
            if not isinstance(raw_voices, list):
                raise ValueError("Fixture page requires a voices array")
            token = raw_page.get("next_page_token") or None
            if token is not None and not isinstance(token, str):
                raise ValueError("Fixture page token must be a string")
            voices = tuple(v for raw in raw_voices if (v := normalize_voice(raw)) is not None)
            self._pages[expected_token] = VoicePage(voices, token)
            if index < len(pages) - 1 and token is None:
                raise ValueError("Fixture has unreachable pages")
            expected_token = token
        if expected_token is not None:
            raise ValueError("Fixture ends with an incomplete scan")
        self._details = fixture.get("details", {})
        if not isinstance(self._details, dict):
            raise ValueError("Fixture details must be an object")

    def list_page(self, page_token: str | None, page_size: int) -> VoicePage:
        if page_token not in self._pages:
            raise ValueError("Fixture has no page for the requested token")
        return self._pages[page_token]

    def get_voice(self, voice_id: str) -> VoiceMetadata:
        if voice_id in self._details:
            result = normalize_voice(self._details[voice_id])
            if result is not None and result.provider_voice_id == voice_id:
                return result
        for page in self._pages.values():
            for voice in page.voices:
                if voice.provider_voice_id == voice_id:
                    return voice
        raise ValueError("Voice is absent from fixture")
