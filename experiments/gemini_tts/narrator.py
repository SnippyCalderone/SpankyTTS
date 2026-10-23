"""Isolated Gemini TTS comparison; synthesis requires an explicit --generate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
import wave


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PASSAGE_PATH = HERE / "passage.json"
PROFILES_PATH = HERE / "profiles.json"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
DEFAULT_VOICE = "Gacrux"

# Only recognized machine-readable provider values may enter run metadata.
# SDK messages, response bodies, request URLs, and headers may contain secrets
# or book text and are never saved or printed.
PROVIDER_CODES = frozenset({
    "INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND",
    "RESOURCE_EXHAUSTED", "FAILED_PRECONDITION", "UNAVAILABLE", "INTERNAL",
    "DEADLINE_EXCEEDED", "UNKNOWN", "CANCELLED", "ABORTED",
})
PROVIDER_REASONS = frozenset({
    "API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_MISSING",
    "BILLING_DISABLED", "BILLING_NOT_ENABLED", "PAYMENT_REQUIRED",
    "QUOTA_EXCEEDED", "RATE_LIMIT_EXCEEDED", "MODEL_NOT_FOUND",
    "SERVICE_DISABLED", "USER_PROJECT_DENIED",
})
DIAGNOSTIC_MESSAGES = {
    "authentication": "The provider rejected authentication; check the configured API key.",
    "permission": "The provider denied access; check project and model permissions.",
    "billing": "The provider reported a billing or payment restriction.",
    "invalid_model_or_resource": "The requested model, voice, or API resource was not found.",
    "invalid_request": "The provider rejected the request; review supported model, voice, and schema.",
    "quota": "The provider reported exhausted quota or capacity for this project.",
    "rate_limit": "The provider reported a rate limit for this project.",
    "quota_or_rate_limit": "The provider returned HTTP 429; quota and rate limits cannot be distinguished from this response.",
    "network": "The request failed at the network or timeout layer.",
    "response_parsing": "The SDK response or returned audio could not be parsed or validated.",
    "provider_service": "The provider returned a server error.",
    "local_io": "The generated output could not be written locally.",
    "unknown": "The request failed before usable audio was returned; the safe fields do not identify the cause.",
}


class LabError(Exception):
    """A safe, user-facing experiment failure."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_passage(config_path: Path = PASSAGE_PATH, root: Path = ROOT) -> tuple[dict, str]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        source_path = root / config["source_file"]
        source = source_path.read_text(encoding="utf-8")
        if sha256_text(source) != config["source_file_sha256"]:
            raise LabError("Source fixture hash does not match")
        start, end = config["start"], config["end"]
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(source)):
            raise LabError("Invalid passage offsets")
        passage = source[start:end]
        if len(passage) != config["length"] or sha256_text(passage) != config["sha256"]:
            raise LabError("Passage length or hash does not match")
        return config, passage
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        raise LabError("Cannot load the fixed local source fixture") from exc


def load_profile(name: str, config_path: Path = PROFILES_PATH) -> tuple[str, str]:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        profile = config["profiles"][name]
        version = f"{config['version']}.{profile['version']}"
        style = profile["style"]
        if not isinstance(style, str) or not style.strip():
            raise LabError("Profile style is empty")
        return version, style
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        raise LabError("Cannot load the requested narration profile") from exc


def build_request(text: str, *, model: str, voice: str, style: str) -> dict:
    if not text or not model.strip() or not voice.strip() or not style.strip():
        raise LabError("Text, model, voice, and style must be nonempty")
    request = {
        "model": model,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}],
            }],
        }],
        "response_format": {"type": "audio", "mime_type": "audio/wav", "sample_rate": 24000},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    if request["input"][0]["content"][0]["text"] != text:
        raise LabError("Request text differs from the source")
    return request


def _field(value: object, name: str) -> object:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def _modality_tokens(value: object) -> list[dict] | None:
    if value is None:
        return None
    return [
        {"modality": str(_field(item, "modality")), "tokens": _field(item, "tokens")}
        for item in value
    ]


def usage_summary(interaction: object) -> dict | None:
    usage = _field(interaction, "usage")
    if usage is None:
        return None
    return {
        "total_input_tokens": _field(usage, "total_input_tokens"),
        "total_output_tokens": _field(usage, "total_output_tokens"),
        "total_tokens": _field(usage, "total_tokens"),
        "input_tokens_by_modality": _modality_tokens(_field(usage, "input_tokens_by_modality")),
        "output_tokens_by_modality": _modality_tokens(_field(usage, "output_tokens_by_modality")),
    }


def _safe_provider_value(value: object, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _provider_fields(exc: Exception) -> tuple[str | None, str | None]:
    body = getattr(exc, "body", None)
    if body is None:
        body = getattr(exc, "details", None)
    if not isinstance(body, dict):
        body = {}
    payload = body.get("error", body)
    if not isinstance(payload, dict):
        payload = {}
    code = _safe_provider_value(getattr(exc, "status", None), PROVIDER_CODES)
    code = code or _safe_provider_value(payload.get("status"), PROVIDER_CODES)
    reason = _safe_provider_value(payload.get("reason"), PROVIDER_REASONS)
    for detail in payload.get("details", []) if isinstance(payload.get("details"), list) else []:
        if isinstance(detail, dict):
            reason = reason or _safe_provider_value(detail.get("reason"), PROVIDER_REASONS)
    return code, reason


def diagnose_error(exc: Exception, stage: str) -> dict:
    """Return fixed, allowlisted diagnostics without serializing SDK error text."""
    class_name = type(exc).__name__
    secret = os.environ.get("GEMINI_API_KEY", "")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", class_name) or (
        secret and secret.lower() in class_name.lower()
    ):
        class_name = "Exception"

    raw_status = getattr(exc, "status_code", None)
    if raw_status is None:
        raw_status = getattr(exc, "code", None)
    if raw_status is None:
        raw_status = getattr(getattr(exc, "response", None), "status_code", None)
    status = raw_status if type(raw_status) is int and 100 <= raw_status <= 599 else None
    provider_code, provider_reason = _provider_fields(exc)

    if provider_reason in {"API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_MISSING"} or (
        status == 401 or provider_code == "UNAUTHENTICATED"
    ):
        kind = "authentication"
    elif provider_reason in {"BILLING_DISABLED", "BILLING_NOT_ENABLED", "PAYMENT_REQUIRED"} or status == 402:
        kind = "billing"
    elif status == 403 or provider_code == "PERMISSION_DENIED":
        kind = "permission"
    elif provider_reason == "MODEL_NOT_FOUND" or status == 404 or provider_code == "NOT_FOUND":
        kind = "invalid_model_or_resource"
    elif provider_reason == "QUOTA_EXCEEDED":
        kind = "quota"
    elif provider_reason == "RATE_LIMIT_EXCEEDED":
        kind = "rate_limit"
    elif status == 429 or provider_code == "RESOURCE_EXHAUSTED":
        kind = "quota_or_rate_limit"
    elif status in {400, 422} or provider_code == "INVALID_ARGUMENT":
        kind = "invalid_request"
    elif class_name in {"APIConnectionError", "APITimeoutError", "ConnectError", "ReadError",
                        "ConnectTimeout", "ReadTimeout", "TimeoutException", "NetworkError"} or (
        stage == "sdk_call" and isinstance(exc, (ConnectionError, TimeoutError, OSError))
    ):
        kind = "network"
    elif class_name in {"APIResponseValidationError", "ResponseValidationError", "ValidationError"} or (
        stage in {"usage_parsing", "response_decoding", "wav_validation"}
    ):
        kind = "response_parsing"
    elif stage == "audio_write" and isinstance(exc, OSError):
        kind = "local_io"
    elif status is not None and status >= 500:
        kind = "provider_service"
    else:
        kind = "unknown"

    return {
        "kind": kind,
        "stage": stage,
        "exception_class": class_name,
        "http_status_code": status,
        "provider_error_code": provider_code,
        "provider_error_reason": provider_reason,
        "diagnostic_message": DIAGNOSTIC_MESSAGES[kind],
    }


def validate_wav(audio: bytes) -> dict:
    try:
        if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise LabError("The response is not a WAV file")
        with wave.open(io.BytesIO(audio), "rb") as reader:
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            sample_rate = reader.getframerate()
            frames = reader.getnframes()
            if (channels, sample_width, sample_rate) != (1, 2, 24000) or frames < 1:
                raise LabError("Unexpected WAV audio properties")
            if reader.getcomptype() != "NONE":
                raise LabError("Compressed WAV audio is unsupported")
            if len(reader.readframes(frames)) != frames * channels * sample_width:
                raise LabError("WAV data is truncated")
        return {
            "encoding": "pcm_s16le", "channels": channels, "sample_width_bytes": sample_width,
            "sample_rate_hz": sample_rate, "frame_count": frames,
            "duration_seconds": frames / sample_rate, "file_bytes": len(audio),
        }
    except (EOFError, ValueError, wave.Error) as exc:
        raise LabError("Invalid WAV audio") from exc


def make_metadata(config: dict, text: str, *, model: str, voice: str,
                  profile: str, profile_version: str, style: str) -> dict:
    return {
        "passage_id": config["id"],
        "source_file": config["source_file"],
        "source_offsets": {"start": config["start"], "end": config["end"]},
        "source_sha256": sha256_text(text),
        "source_character_count": len(text),
        "request_text_sha256": sha256_text(text),
        "model_id": model,
        "narrator_voice": {"provider": "google_gemini", "id": voice},
        "profile": profile,
        "profile_version": profile_version,
        "style_sha256": sha256_text(style),
        "latency_seconds": None,
        "audio": None,
        "usage": None,
        "error": None,
    }


def generate(request: dict, metadata: dict, output_root: Path,
             *, client_factory=None, timer=time.perf_counter) -> Path:
    if not os.environ.get("GEMINI_API_KEY"):
        raise LabError("GEMINI_API_KEY is unavailable to this Python process")
    if client_factory is None:
        from google import genai
        client_factory = genai.Client
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    started = timer()
    client = None
    stage = "client_initialization"
    try:
        # Pass the intended key explicitly if GOOGLE_API_KEY also exists.
        client = client_factory(api_key=os.environ["GEMINI_API_KEY"])
        stage = "sdk_call"
        interaction = client.interactions.create(**request)
        stage = "usage_parsing"
        metadata["usage"] = usage_summary(interaction)
        stage = "response_decoding"
        audio_data = _field(_field(interaction, "output_audio"), "data")
        if not isinstance(audio_data, str) or not audio_data:
            raise LabError("The API returned no audio")
        try:
            audio = base64.b64decode(audio_data, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise LabError("The API returned invalid audio data") from exc
        stage = "wav_validation"
        metadata["audio"] = validate_wav(audio)
        stage = "audio_write"
        (run_dir / "narration.wav").write_bytes(audio)
    except Exception as exc:
        metadata["error"] = diagnose_error(exc, stage)
        raise LabError(metadata["error"]["diagnostic_message"] + " See run.json for safe details.") from exc
    finally:
        metadata["latency_seconds"] = round(timer() - started, 6)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        try:
            (run_dir / "run.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except (OSError, TypeError, ValueError) as exc:
            raise LabError("Cannot save run metadata") from exc
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fixed-passage Gemini narrator comparison")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and preview without an API call")
    mode.add_argument("--generate", action="store_true", help="Make one audio-generating API call")
    parser.add_argument("--profile", choices=("neutral", "character_aware"), required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--output-dir", type=Path, default=HERE / "output")
    args = parser.parse_args(argv)
    try:
        config, text = load_passage()
        version, style = load_profile(args.profile)
        request = build_request(text, model=args.model, voice=args.voice, style=style)
        metadata = make_metadata(config, text, model=args.model, voice=args.voice,
                                 profile=args.profile, profile_version=version, style=style)
        if args.dry_run:
            print(json.dumps({**metadata, "mode": "dry_run", "request_text_matches_source":
                              request["input"][0]["content"][0]["text"] == text}, indent=2))
        else:
            run_dir = generate(request, metadata, args.output_dir)
            print(f"Saved WAV and metadata: {run_dir}")
        return 0
    except (LabError, OSError) as exc:
        if isinstance(exc, OSError):
            exc = LabError("Cannot create the output directory")
        print(f"Gemini Narrator Lab: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
