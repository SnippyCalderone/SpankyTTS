import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chapter_tts as experiment


def make_epub(path: Path) -> None:
    container = '''<?xml version="1.0"?>
    <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
    </container>'''
    package = '''<?xml version="1.0"?>
    <package xmlns="http://www.idpf.org/2007/opf">
      <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture Book</dc:title></metadata>
      <manifest>
        <item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>
        <item id="first" href="one.xhtml" media-type="application/xhtml+xml"/>
        <item id="second" href="two.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
      <spine><itemref idref="first"/><itemref idref="second"/></spine>
    </package>'''
    nav = '''<html><body><nav epub:type="toc"><ol>
      <li><a href="one.xhtml#chapter-one">Chapter One</a></li>
      <li><a href="one.xhtml#chapter-two">Chapter Two</a></li>
      <li><a href="two.xhtml#chapter-three">Chapter Three</a></li>
    </ol></nav></body></html>'''
    one = '''<html><body>
      <h1 id="chapter-one">Chapter One</h1>
      <p>“Hello,” said Ada. <em>Really?</em> Yes!</p>
      <p>First chapter, second paragraph.</p>
      <h1 id="chapter-two">Chapter Two</h1>
      <p>Mr. Poe asked, “Are we ready?”</p>
      <p>We are ready—now.</p>
    </body></html>'''
    two = '''<html><body>
      <h1 id="chapter-three">Chapter Three</h1>
      <p>The end. No more chapters.</p>
    </body></html>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/nav.xhtml", nav)
        archive.writestr("OEBPS/one.xhtml", one)
        archive.writestr("OEBPS/two.xhtml", two)


class ChapterExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.epub = Path(self.temporary.name) / "fixture.epub"
        make_epub(self.epub)

    def test_chapter_listing_follows_spine_and_navigation_anchors(self):
        book, chapters = experiment.list_chapters(self.epub)
        self.assertEqual("Fixture Book", book)
        self.assertEqual(["Chapter One", "Chapter Two", "Chapter Three"], [chapter.title for chapter in chapters])
        self.assertNotIn("Available chapters", " ".join(chapter.text for chapter in chapters))

    def test_extraction_preserves_paragraphs_dialogue_and_chapter_span(self):
        _, chapters = experiment.list_chapters(self.epub)
        self.assertIn("“Hello,” said Ada. Really? Yes!\n\nFirst chapter, second paragraph.", chapters[0].text)
        self.assertNotIn("Mr. Poe", chapters[0].text)
        self.assertIn("Mr. Poe asked, “Are we ready?”\n\nWe are ready—now.", chapters[1].text)
        self.assertNotIn("The end", chapters[1].text)
        self.assertIn("The end. No more chapters.", chapters[2].text)

    def test_block_plan_preserves_every_character_and_prefers_paragraphs(self):
        paragraph = "A deliberate, complete sentence. " * 31
        text = "\n\n".join([paragraph] * 9)
        blocks = experiment.plan_blocks(text)
        self.assertEqual(text, "".join(blocks))
        self.assertTrue(all(len(block) <= experiment.BLOCK_TARGET for block in blocks))
        self.assertTrue(blocks[0].endswith("\n\n"))
        self.assertGreater(len(blocks), 1)

    def test_short_terminal_dialogue_starts_next_block(self):
        paragraph = ("story words flow " * 19).strip()
        for dialogue in ("“You do?” Klaus said.", "“Deepo!”"):
            with self.subTest(dialogue=dialogue):
                text = "\n\n".join([paragraph] * 3 + [dialogue] + [paragraph] * 3)
                blocks = experiment.plan_blocks(text, target=1000)
                self.assertEqual("\n\n".join([paragraph] * 3) + "\n\n", blocks[0])
                self.assertTrue(blocks[1].startswith(dialogue + "\n\n"))
                self.assertEqual(text, "".join(blocks))
                self.assertTrue(all(len(block) <= 1000 and len(block) <= experiment.HARD_INPUT_LIMIT for block in blocks))

    def test_short_final_chapter_paragraph_is_unchanged(self):
        paragraph = ("story words flow " * 19).strip()
        text = "\n\n".join([paragraph] * 4 + ["“Deepo!”"])
        blocks = experiment.plan_blocks(text, target=1000)
        self.assertGreater(len(blocks), 1)
        self.assertTrue(blocks[-1].endswith("“Deepo!”"))
        self.assertEqual(text, "".join(blocks))
        self.assertTrue(all(len(block) <= 1000 and len(block) <= experiment.HARD_INPUT_LIMIT for block in blocks))

    def test_tail_protection_threshold_is_inclusive(self):
        paragraph = ("story words flow " * 19).strip()
        prefix = "\n\n".join([paragraph] * 3) + "\n\n"
        for tail_length, should_move in ((120, True), (121, False)):
            with self.subTest(tail_length=tail_length):
                tail = "a " * 59 + ("ab" if should_move else "abc")
                self.assertEqual(tail_length, len(tail))
                text = prefix + tail + "\n\n" + paragraph * 2
                blocks = experiment.plan_blocks(text, target=1200)
                self.assertEqual(should_move, blocks[1].startswith(tail))
                self.assertEqual(text, "".join(blocks))
                self.assertTrue(all(len(block) <= 1200 and len(block) <= experiment.HARD_INPUT_LIMIT for block in blocks))

    def test_oversized_paragraph_falls_back_to_sentence_then_word(self):
        text = ("Mr. Poe asked, “Are we ready?” The door opened. " * 130).strip()
        blocks = experiment.plan_blocks(text)
        self.assertEqual(text, "".join(blocks))
        self.assertTrue(all(len(block) <= experiment.BLOCK_TARGET for block in blocks))
        self.assertTrue(blocks[0].rstrip().endswith((".", "?”")))
        long_sentence = "word " * 900
        word_blocks = experiment.plan_blocks(long_sentence.strip())
        self.assertEqual(long_sentence.strip(), "".join(word_blocks))
        self.assertTrue(all(len(block) <= experiment.BLOCK_TARGET for block in word_blocks))

    def test_decline_path_never_generates_or_creates_output(self):
        out = io.StringIO()
        with patch("builtins.input", side_effect=["2", "N"]), patch.object(experiment, "generate") as generate:
            with contextlib.redirect_stdout(out):
                result = experiment.main(["--epub", str(self.epub)])
        self.assertEqual(0, result)
        generate.assert_not_called()
        self.assertIn("Generation declined. No API requests made.", out.getvalue())

    def test_profile_instructions_have_valid_size_and_settings(self):
        profile, instructions = experiment.load_profile()
        self.assertEqual("gpt-4o-mini-tts", profile["model"])
        self.assertEqual("cedar", profile["voice"])
        self.assertEqual(1.0, profile["speed"])
        self.assertIn("Cadence:", instructions)
        self.assertIn("Whispering:", instructions)
        for field in ("text_fidelity", "ending_fidelity", "dialogue_tags", "interruptions", "scene_dynamics"):
            with self.subTest(field=field):
                self.assertIn(f"{field.replace('_', ' ').title()}: {profile[field]}", instructions)
        self.assertIn("Read every word in the provided input exactly once.", instructions)
        self.assertIn("The final sentence and final words of the input must be spoken completely.", instructions)
        self.assertLessEqual(len(instructions), experiment.HARD_INSTRUCTIONS_LIMIT)

    def test_new_profile_fields_are_required_and_nonempty(self):
        profile, _ = experiment.load_profile()
        path = Path(self.temporary.name) / "profile.json"
        for field in ("text_fidelity", "ending_fidelity", "dialogue_tags", "interruptions", "scene_dynamics"):
            for value in (None, ""):
                with self.subTest(field=field, value=value):
                    altered = profile.copy()
                    if value is None:
                        del altered[field]
                    else:
                        altered[field] = value
                    path.write_text(json.dumps(altered), encoding="utf-8")
                    with self.assertRaises(experiment.ExperimentError):
                        experiment.load_profile(path)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_mp3_probe_and_lossless_concat(self):
        base = Path(self.temporary.name)
        parts = [base / "part_001.mp3", base / "part_002.mp3"]
        for path in parts:
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=0.25", "-q:a", "5", str(path),
            ], check=True, capture_output=True)
        combined = base / "chapter_complete.mp3"
        experiment.concatenate_mp3(parts, combined)
        self.assertTrue(combined.is_file())
        self.assertGreater(experiment.probe_duration(combined), 0.45)
        self.assertGreater(combined.stat().st_size, parts[0].stat().st_size)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg tools unavailable")
    def test_mocked_generation_saves_exact_text_and_summary_without_api(self):
        base = Path(self.temporary.name)
        fixture_mp3 = base / "fixture.mp3"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=0.25", "-q:a", "5", str(fixture_mp3),
        ], check=True, capture_output=True)
        chapter = experiment.Chapter("Chapter Two", "Hello. World!")
        blocks = ["Hello. ", "World!"]
        profile, instructions = experiment.load_profile()
        output_root = base / "output"
        with patch("dotenv.load_dotenv") as load_dotenv, patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}):
            with patch("openai.OpenAI") as client_factory, patch.object(experiment, "OUTPUT_ROOT", output_root):
                response = client_factory.return_value.audio.speech.with_streaming_response.create.return_value.__enter__.return_value
                response.stream_to_file.side_effect = lambda destination: shutil.copyfile(fixture_mp3, destination)
                with contextlib.redirect_stdout(io.StringIO()):
                    run_dir = experiment.generate(self.epub, "Fixture Book", chapter, blocks, profile, instructions)
        load_dotenv.assert_called_once()
        self.assertEqual(chapter.text, (run_dir / "chapter_source.txt").read_text(encoding="utf-8"))
        self.assertEqual(blocks, [(run_dir / f"part_{index:03d}.txt").read_text(encoding="utf-8") for index in (1, 2)])
        summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual("complete", summary["status"])
        self.assertEqual([7, 6], summary["characters_per_block"])
        self.assertEqual(2, summary["number_of_blocks"])
        self.assertEqual(profile, summary["narration_profile"])
        self.assertEqual(instructions, summary["instructions"])
        self.assertEqual(2, len(summary["parts"]))
        self.assertGreater(summary["total_audio_duration_seconds"], 0)
        self.assertGreater(summary["total_mp3_filesize_bytes"], 0)
        self.assertTrue((run_dir / "chapter_complete.mp3").is_file())
        self.assertEqual(2, client_factory.return_value.audio.speech.with_streaming_response.create.call_count)
        self.assertEqual(0, client_factory.call_args.kwargs["max_retries"])
        for call in client_factory.return_value.audio.speech.with_streaming_response.create.call_args_list:
            self.assertEqual(instructions, call.kwargs["instructions"])


if __name__ == "__main__":
    unittest.main()
