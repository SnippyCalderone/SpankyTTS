import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT_DIR))
from test_chapter_tts import make_epub

import chapter_tts as chapter
import diagnose_final as diagnostic


class FinalDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.epub = self.root / "fixture.epub"
        make_epub(self.epub)
        self.book, self.chapters = chapter.list_chapters(self.epub)

    def test_plan_uses_exact_final_paragraph_and_real_next_section_prefix(self):
        plan = diagnostic.make_plan(self.book, self.chapters, 1)
        self.assertEqual("We are ready—now.", plan.test_a)
        self.assertEqual(self.chapters[1].text[plan.final_paragraph_start:], plan.test_a)
        self.assertEqual(self.chapters[2].text[:len(plan.following_text)], plan.following_text)
        self.assertEqual(plan.test_a + "\n\n" + plan.following_text, plan.test_b)
        self.assertIn("Chapter Three", plan.following_text)
        self.assertLessEqual(len(plan.test_a), chapter.BLOCK_TARGET)
        self.assertLessEqual(len(plan.test_b), chapter.BLOCK_TARGET)
        self.assertLessEqual(len(plan.test_b), chapter.HARD_INPUT_LIMIT)

    def test_following_prefix_uses_natural_boundary_without_rewriting(self):
        text = "Chapter Six\n\n" + ("The next section begins with genuine prose. " * 16)
        prefix = diagnostic.take_following_prefix(text, maximum=180)
        self.assertTrue(text.startswith(prefix))
        self.assertLessEqual(len(prefix), 180)
        self.assertTrue(prefix.endswith(("\n\n", ". ")))

    def test_last_readable_section_cannot_be_diagnosed(self):
        with self.assertRaises(chapter.ExperimentError):
            diagnostic.make_plan(self.book, self.chapters, len(self.chapters) - 1)

    def test_decline_prints_boundaries_and_makes_no_request(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=["2", "N"]), patch.object(diagnostic, "generate") as generate:
            with contextlib.redirect_stdout(output):
                result = diagnostic.main(["--epub", str(self.epub)])
        self.assertEqual(0, result)
        generate.assert_not_called()
        self.assertIn("extracted character offsets", output.getvalue())
        self.assertIn("Exact following EPUB text appended", output.getvalue())
        self.assertIn("Estimated API requests: exactly 2", output.getvalue())
        self.assertIn("No API requests made", output.getvalue())

    def test_fidelity_instructions_are_not_duplicated_in_current_profile(self):
        profile, baseline = chapter.load_profile()
        combined = diagnostic.make_fidelity_instructions(profile, baseline)
        self.assertEqual(baseline, combined)
        self.assertIn("Read every word in the provided input exactly once.", combined)
        self.assertIn("The final sentence and final words of the input must be spoken completely.", combined)
        self.assertEqual(1, combined.count("Read every word in the provided input exactly once."))
        self.assertLessEqual(len(combined), chapter.HARD_INSTRUCTIONS_LIMIT)
        with self.assertRaises(chapter.ExperimentError):
            diagnostic.make_fidelity_instructions({**profile, "voice": "alloy"}, baseline)

    def test_fidelity_decline_previews_exact_test_a_and_one_request(self):
        plan = diagnostic.make_plan(self.book, self.chapters, 1)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["2", "N"]), patch.object(diagnostic, "generate_fidelity") as generate:
            with contextlib.redirect_stdout(output):
                result = diagnostic.main(["--epub", str(self.epub), "--test-c-fidelity"])
        self.assertEqual(0, result)
        generate.assert_not_called()
        self.assertIn(plan.test_a, output.getvalue())
        self.assertIn("Text Fidelity:", output.getvalue())
        self.assertIn("Ending Fidelity:", output.getvalue())
        self.assertIn("Read every word in the provided input exactly once.", output.getvalue())
        self.assertIn("Estimated API requests: exactly 1 paid request", output.getvalue())
        self.assertIn("No API requests made", output.getvalue())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_mocked_two_case_generation_saves_exact_inputs_and_metadata(self):
        fixture_mp3 = self.root / "fixture.mp3"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.25", "-q:a", "5", str(fixture_mp3),
        ], check=True, capture_output=True)
        plan = diagnostic.make_plan(self.book, self.chapters, 1)
        profile, instructions = chapter.load_profile()
        with patch("dotenv.load_dotenv"), patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}):
            with patch("openai.OpenAI") as client_factory, patch.object(diagnostic, "DIAGNOSTIC_OUTPUT", self.root / "diagnostics"):
                response = client_factory.return_value.audio.speech.with_streaming_response.create.return_value.__enter__.return_value
                response.stream_to_file.side_effect = lambda path: shutil.copyfile(fixture_mp3, path)
                with contextlib.redirect_stdout(io.StringIO()):
                    run_dir = diagnostic.generate(self.epub, plan, profile, instructions)
        self.assertEqual(plan.test_a, (run_dir / "test_a_final_paragraph.txt").read_text(encoding="utf-8"))
        self.assertEqual(plan.test_b, (run_dir / "test_b_with_following.txt").read_text(encoding="utf-8"))
        self.assertTrue((run_dir / "test_a_final_paragraph.mp3").is_file())
        self.assertTrue((run_dir / "test_b_with_following.mp3").is_file())
        summary = json.loads((run_dir / "diagnostic_summary.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", summary["status"])
        self.assertEqual(2, summary["planned_api_requests"])
        self.assertEqual(2, summary["completed_api_requests"])
        self.assertEqual([0, len(plan.following_text)], summary["source_boundaries"]["test_b_following_character_offsets"])
        self.assertEqual(2, len(summary["cases"]))
        self.assertTrue(all(case["duration_seconds"] > 0 for case in summary["cases"]))
        self.assertEqual(0, client_factory.call_args.kwargs["max_retries"])
        calls = client_factory.return_value.audio.speech.with_streaming_response.create.call_args_list
        self.assertEqual([plan.test_a, plan.test_b], [call.kwargs["input"] for call in calls])
        for call in calls:
            self.assertEqual(profile["model"], call.kwargs["model"])
            self.assertEqual(profile["voice"], call.kwargs["voice"])
            self.assertEqual(profile["speed"], call.kwargs["speed"])
            self.assertEqual(instructions, call.kwargs["instructions"])
            self.assertEqual("mp3", call.kwargs["response_format"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_mocked_test_c_saves_exact_input_instructions_mp3_and_metadata(self):
        fixture_mp3 = self.root / "fixture_c.mp3"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.25", "-q:a", "5", str(fixture_mp3),
        ], check=True, capture_output=True)
        plan = diagnostic.make_plan(self.book, self.chapters, 1)
        profile, baseline = chapter.load_profile()
        combined = diagnostic.make_fidelity_instructions(profile, baseline)
        with patch("dotenv.load_dotenv"), patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}):
            with patch("openai.OpenAI") as client_factory, patch.object(diagnostic, "DIAGNOSTIC_OUTPUT", self.root / "diagnostics_c"):
                response = client_factory.return_value.audio.speech.with_streaming_response.create.return_value.__enter__.return_value
                response.stream_to_file.side_effect = lambda path: shutil.copyfile(fixture_mp3, path)
                with contextlib.redirect_stdout(io.StringIO()):
                    run_dir = diagnostic.generate_fidelity(self.epub, plan, profile, combined)
        stem = diagnostic.TEST_C_STEM
        self.assertEqual(plan.test_a, (run_dir / f"{stem}.txt").read_text(encoding="utf-8"))
        self.assertEqual(combined, (run_dir / f"{stem}.instructions.txt").read_text(encoding="utf-8"))
        self.assertTrue((run_dir / f"{stem}.mp3").is_file())
        summary = json.loads((run_dir / f"{stem}.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", summary["status"])
        self.assertEqual(1, summary["planned_api_requests"])
        self.assertEqual(len(plan.test_a), summary["character_count"])
        self.assertEqual(profile["model"], summary["model"])
        self.assertEqual(profile["voice"], summary["voice"])
        self.assertEqual(profile["speed"], summary["speed"])
        self.assertGreater(summary["duration_seconds"], 0)
        self.assertGreaterEqual(summary["generation_time_seconds"], 0)
        self.assertEqual(0, client_factory.call_args.kwargs["max_retries"])
        calls = client_factory.return_value.audio.speech.with_streaming_response.create.call_args_list
        self.assertEqual(1, len(calls))
        self.assertEqual(plan.test_a, calls[0].kwargs["input"])
        self.assertEqual(combined, calls[0].kwargs["instructions"])
        self.assertEqual(profile["model"], calls[0].kwargs["model"])
        self.assertEqual(profile["voice"], calls[0].kwargs["voice"])
        self.assertEqual(profile["speed"], calls[0].kwargs["speed"])


if __name__ == "__main__":
    unittest.main()
