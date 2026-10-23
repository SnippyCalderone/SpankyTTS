"""Mock-only tests. No test uses the Gemini service."""

import base64
import httpx
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import wave

from google.genai import errors as legacy_errors
from google.genai._gaos.lib import compat_errors
from google.genai._gaos.types.interactions.createmodelinteraction import CreateModelInteraction


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import narrator  # noqa: E402


def example_wav(sample_rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * 240)
    return buffer.getvalue()


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.closed = False
        self.interactions = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result

    def close(self):
        self.closed = True


class NarratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.text = narrator.load_passage()

    def test_fixed_passage_and_both_profiles_preserve_exact_text(self):
        self.assertEqual((3623, 4232), (self.config["start"], self.config["end"]))
        self.assertEqual(609, len(self.text))
        self.assertEqual(self.config["sha256"], narrator.sha256_text(self.text))
        requests = []
        for profile in ("neutral", "character_aware"):
            version, style = narrator.load_profile(profile)
            self.assertEqual("1.1", version)
            requests.append(narrator.build_request(
                self.text, model=narrator.DEFAULT_MODEL, voice=narrator.DEFAULT_VOICE, style=style
            ))
        self.assertNotEqual(requests[0]["input"][0]["content"][0]["annotations"],
                            requests[1]["input"][0]["content"][0]["annotations"])
        for request in requests:
            self.assertEqual(self.text, request["input"][0]["content"][0]["text"])
            self.assertEqual([{"voice": "Gacrux"}], request["generation_config"]["speech_config"])
            self.assertEqual("gemini-3.8-flash-tts", request["model"])
            self.assertEqual({"type": "audio", "mime_type": "audio/wav", "sample_rate": 24000},
                             request["response_format"])

    def test_request_validates_against_installed_sdk_schema_without_api_call(self):
        version, style = narrator.load_profile("neutral")
        self.assertEqual("1.1", version)
        request = narrator.build_request(
            self.text, model=narrator.DEFAULT_MODEL, voice=narrator.DEFAULT_VOICE, style=style
        )
        parsed = CreateModelInteraction.model_validate(request)
        serialized = parsed.model_dump(mode="json", exclude_none=True)
        self.assertEqual(self.text, serialized["input"][0]["content"][0]["text"])
        self.assertEqual([{"voice": "Gacrux"}], serialized["generation_config"]["speech_config"])
        self.assertEqual("audio/wav", serialized["response_format"]["mime_type"])

    def test_dry_run_does_not_call_generation_or_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with mock.patch.object(narrator, "generate", side_effect=AssertionError("API called")):
                for profile in ("neutral", "character_aware"):
                    with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                        result = narrator.main([
                            "--dry-run", "--profile", profile, "--output-dir", str(output)
                        ])
                    report = json.loads(stdout.getvalue())
                    self.assertEqual(0, result)
                    self.assertTrue(report["request_text_matches_source"])
                    self.assertEqual(self.config["sha256"], report["request_text_sha256"])
            self.assertFalse(output.exists())

    def test_mocked_generation_saves_valid_wav_and_metadata(self):
        version, style = narrator.load_profile("neutral")
        request = narrator.build_request(self.text, model="test-model", voice="test-voice", style=style)
        metadata = narrator.make_metadata(self.config, self.text, model="test-model", voice="test-voice",
                                          profile="neutral", profile_version=version, style=style)
        wav_data = example_wav()
        result = SimpleNamespace(
            output_audio=SimpleNamespace(data=base64.b64encode(wav_data).decode("ascii")),
            usage=SimpleNamespace(total_input_tokens=120, total_output_tokens=25, total_tokens=145,
                                  input_tokens_by_modality=[{"modality": "text", "tokens": 120}],
                                  output_tokens_by_modality=[{"modality": "audio", "tokens": 25}]),
        )
        fake = FakeClient(result=result)
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}):
            run_dir = narrator.generate(request, metadata, Path(temp), client_factory=lambda **_: fake)
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(wav_data, (run_dir / "narration.wav").read_bytes())
            self.assertEqual([request], fake.calls)
            self.assertTrue(fake.closed)
            self.assertEqual(self.config["sha256"], saved["source_sha256"])
            self.assertEqual({"start": 3623, "end": 4232}, saved["source_offsets"])
            self.assertEqual("test-model", saved["model_id"])
            self.assertEqual({"provider": "google_gemini", "id": "test-voice"}, saved["narrator_voice"])
            self.assertEqual(240, saved["audio"]["frame_count"])
            self.assertEqual(24000, saved["audio"]["sample_rate_hz"])
            self.assertEqual(120, saved["usage"]["total_input_tokens"])
            self.assertEqual(25, saved["usage"]["output_tokens_by_modality"][0]["tokens"])
            self.assertIsNone(saved["error"])
            self.assertIsNotNone(saved["latency_seconds"])

    def test_invalid_wav_is_rejected_and_error_metadata_is_saved(self):
        version, style = narrator.load_profile("neutral")
        request = narrator.build_request(self.text, model="model", voice="voice", style=style)
        metadata = narrator.make_metadata(self.config, self.text, model="model", voice="voice",
                                          profile="neutral", profile_version=version, style=style)
        result = SimpleNamespace(output_audio=SimpleNamespace(data=base64.b64encode(b"not wav").decode()),
                                 usage=None)
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-secret"}):
            with self.assertRaises(narrator.LabError):
                narrator.generate(request, metadata, Path(temp), client_factory=lambda **_: FakeClient(result=result))
            run_dir = next(Path(temp).iterdir())
            self.assertFalse((run_dir / "narration.wav").exists())
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual("response_parsing", saved["error"]["kind"])
            self.assertEqual("wav_validation", saved["error"]["stage"])
            self.assertEqual("LabError", saved["error"]["exception_class"])
            self.assertIsNone(saved["usage"])

    def test_wav_rejects_unexpected_sample_rate_and_truncated_data(self):
        with self.assertRaisesRegex(narrator.LabError, "Unexpected WAV"):
            narrator.validate_wav(example_wav(sample_rate=16000))
        with self.assertRaisesRegex(narrator.LabError, "truncated"):
            narrator.validate_wav(example_wav()[:-8])

    def test_api_error_never_records_exception_message_or_key(self):
        version, style = narrator.load_profile("neutral")
        request = narrator.build_request(self.text, model="model", voice="voice", style=style)
        metadata = narrator.make_metadata(self.config, self.text, model="model", voice="voice",
                                          profile="neutral", profile_version=version, style=style)
        fake = FakeClient(error=RuntimeError("secret-example from provider"))
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GEMINI_API_KEY": "secret-example"}):
            with self.assertRaises(narrator.LabError) as caught:
                narrator.generate(request, metadata, Path(temp), client_factory=lambda **_: fake)
            saved = (next(Path(temp).iterdir()) / "run.json").read_text(encoding="utf-8")
            self.assertNotIn("secret-example", str(caught.exception))
            self.assertNotIn("secret-example", saved)
            error = json.loads(saved)["error"]
            self.assertEqual("unknown", error["kind"])
            self.assertEqual("RuntimeError", error["exception_class"])
            self.assertEqual("sdk_call", error["stage"])

    def test_sdk_http_errors_have_safe_category_status_and_provider_code(self):
        cases = [
            (401, "UNAUTHENTICATED", None, "authentication"),
            (403, "PERMISSION_DENIED", None, "permission"),
            (402, "FAILED_PRECONDITION", "BILLING_DISABLED", "billing"),
            (404, "NOT_FOUND", None, "invalid_model_or_resource"),
            (400, "INVALID_ARGUMENT", None, "invalid_request"),
            (429, "RESOURCE_EXHAUSTED", "QUOTA_EXCEEDED", "quota"),
            (429, "RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED", "rate_limit"),
            (429, "RESOURCE_EXHAUSTED", None, "quota_or_rate_limit"),
            (503, "UNAVAILABLE", None, "provider_service"),
        ]
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "secret-example"}):
            for status, code, reason, kind in cases:
                with self.subTest(status=status, reason=reason):
                    request = httpx.Request("POST", "https://example.invalid/?key=secret-example",
                                            content="private source passage")
                    response = httpx.Response(status, request=request)
                    body = {"error": {"status": code, "message": "Bearer secret-example private source passage"}}
                    if reason:
                        body["error"]["details"] = [{"reason": reason}]
                    exc = compat_errors.APIError.generate(
                        status_code=status, body=body, message="Bearer secret-example private source passage",
                        response=response,
                    )
                    diagnostic = narrator.diagnose_error(exc, "sdk_call")
                    self.assertEqual(kind, diagnostic["kind"])
                    self.assertEqual(status, diagnostic["http_status_code"])
                    self.assertEqual(code, diagnostic["provider_error_code"])
                    self.assertEqual(reason, diagnostic["provider_error_reason"])
                    serialized = json.dumps(diagnostic)
                    self.assertNotIn("secret-example", serialized)
                    self.assertNotIn("private source passage", serialized)
                    self.assertNotIn("Bearer", serialized)

    def test_legacy_sdk_and_connection_errors_are_classified_without_messages(self):
        legacy = legacy_errors.ClientError(
            403, {"error": {"status": "PERMISSION_DENIED", "message": "secret-example"}}
        )
        diagnostic = narrator.diagnose_error(legacy, "sdk_call")
        self.assertEqual("permission", diagnostic["kind"])
        self.assertEqual("ClientError", diagnostic["exception_class"])
        self.assertEqual(403, diagnostic["http_status_code"])
        self.assertEqual("PERMISSION_DENIED", diagnostic["provider_error_code"])

        request = httpx.Request("POST", "https://example.invalid/?key=secret-example")
        connection = compat_errors.APIConnectionError(message="Bearer secret-example", request=request)
        diagnostic = narrator.diagnose_error(connection, "sdk_call")
        self.assertEqual("network", diagnostic["kind"])
        self.assertIsNone(diagnostic["http_status_code"])
        self.assertNotIn("secret-example", json.dumps(diagnostic))

        response = httpx.Response(200, request=request)
        parse_error = compat_errors.APIResponseValidationError(
            response, {"input": "private source passage"}, message="Bearer secret-example"
        )
        diagnostic = narrator.diagnose_error(parse_error, "sdk_call")
        self.assertEqual("response_parsing", diagnostic["kind"])
        self.assertEqual(200, diagnostic["http_status_code"])
        self.assertNotIn("private source passage", json.dumps(diagnostic))

        diagnostic = narrator.diagnose_error(OSError("secret-example"), "audio_write")
        self.assertEqual("local_io", diagnostic["kind"])
        self.assertNotIn("secret-example", json.dumps(diagnostic))

    def test_missing_key_and_changed_source_fail_before_api_call(self):
        version, style = narrator.load_profile("neutral")
        request = narrator.build_request(self.text, model="model", voice="voice", style=style)
        metadata = narrator.make_metadata(self.config, self.text, model="model", voice="voice",
                                          profile="neutral", profile_version=version, style=style)
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(narrator.LabError, "unavailable"):
                narrator.generate(request, metadata, Path(temp), client_factory=lambda **_: self.fail("API called"))
            self.assertEqual([], list(Path(temp).iterdir()))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "passage.json"
            config_path.write_text(json.dumps(self.config), encoding="utf-8")
            source = root / self.config["source_file"]
            source.parent.mkdir(parents=True)
            source.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(narrator.LabError, "fixture hash"):
                narrator.load_passage(config_path, root)


if __name__ == "__main__":
    unittest.main()
