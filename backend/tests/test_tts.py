import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Project rules forbid opening backend/.env during automated tests.
with patch("dotenv.load_dotenv", return_value=False):
    from app import main


class TTSRequestTests(unittest.TestCase):
    def synthesize(self, payload):
        client = MagicMock()
        client.audio.speech.with_streaming_response.create.return_value.__enter__.return_value.read.return_value = b"\x00\x00"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}):
            with patch.object(main, "OpenAI", return_value=client):
                response = main.tts(payload)
        kwargs = client.audio.speech.with_streaming_response.create.call_args.kwargs
        return response, kwargs

    def test_context_stays_out_of_exact_speech_input(self):
        speech = "  And of course,  "
        response, kwargs = self.synthesize(
            main.TTSRequest(
                text=speech,
                previous_context="The narrator paused.",
                following_context="the travelers carried on.",
            )
        )
        self.assertEqual(speech, kwargs["input"])
        self.assertIn("The narrator paused.", kwargs["instructions"])
        self.assertIn("the travelers carried on.", kwargs["instructions"])
        self.assertNotIn("The narrator paused.", kwargs["input"])
        self.assertEqual(b"\x00\x00", response.body)
        self.assertEqual("24000", response.headers["X-Audio-Sample-Rate"])

    def test_without_context_keeps_previous_instructions(self):
        _, kwargs = self.synthesize(main.TTSRequest(text="Hello.", instructions="Read naturally."))
        self.assertEqual("Hello.", kwargs["input"])
        self.assertEqual("Read naturally.", kwargs["instructions"])

    def test_blank_text_and_oversized_context_are_rejected(self):
        with self.assertRaises(HTTPException) as blank:
            main.tts(main.TTSRequest(text=" \n "))
        self.assertEqual(400, blank.exception.status_code)

        with self.assertRaises(HTTPException) as oversized:
            main.tts(main.TTSRequest(text="Hello.", previous_context="x" * 241))
        self.assertEqual(413, oversized.exception.status_code)


if __name__ == "__main__":
    unittest.main()
