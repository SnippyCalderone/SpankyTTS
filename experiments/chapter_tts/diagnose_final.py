"""Isolated diagnostics for an omitted final chapter sentence."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import chapter_tts as chapter


FOLLOWING_CONTEXT_CHARS = 300
DIAGNOSTIC_OUTPUT = chapter.OUTPUT_ROOT / "diagnostics"
FIDELITY_ADDENDUM = (
    "Text Fidelity:\n"
    "Read every word in the provided input exactly once.\n"
    "Do not omit, skip, summarize, paraphrase, truncate, or add words.\n"
    "Continue through the complete input until the final word has been spoken.\n\n"
    "Ending Fidelity:\n"
    "Do not stop early.\n"
    "The final sentence and final words of the input must be spoken completely."
)
FIDELITY_SENTENCES = (
    "Read every word in the provided input exactly once.",
    "Do not omit, skip, summarize, paraphrase, truncate, or add words.",
    "Continue through the complete input until the final word has been spoken.",
    "Do not stop early.",
    "The final sentence and final words of the input must be spoken completely.",
)
TEST_C_STEM = "test_c_final_paragraph_with_fidelity"


@dataclass(frozen=True)
class DiagnosticPlan:
    book: str
    chapter_title: str
    chapter_number: int
    chapter_chars: int
    final_paragraph_start: int
    final_paragraph: str
    next_title: str
    next_number: int
    following_text: str

    @property
    def test_a(self) -> str:
        return self.final_paragraph

    @property
    def test_b(self) -> str:
        return self.final_paragraph + "\n\n" + self.following_text


def take_following_prefix(text: str, maximum: int = FOLLOWING_CONTEXT_CHARS) -> str:
    """Return an exact source prefix, favoring complete paragraphs or sentences."""
    if not text.strip():
        raise chapter.ExperimentError("The following EPUB section has no readable text")
    if maximum < 1:
        raise chapter.ExperimentError("No room remains for real following EPUB text")
    if len(text) <= maximum:
        return text
    minimum = min(100, maximum // 2)
    window = text[:maximum]
    paragraph_ends = [match.end() for match in re.finditer(r"\n\n", window)]
    sentence_ends = chapter.sentence_breaks(text, 0, maximum)
    word_ends = [match.end() for match in re.finditer(r"\s+", window)]
    boundary = next((positions[-1] for positions in (paragraph_ends, sentence_ends, word_ends)
                     if positions and positions[-1] >= minimum), None)
    if boundary is None:
        boundary = word_ends[-1] if word_ends else None
    if boundary is None:
        raise chapter.ExperimentError("The following EPUB section begins with a word too long for the diagnostic")
    return text[:boundary]


def make_plan(book: str, chapters: list[chapter.Chapter], selected: int) -> DiagnosticPlan:
    if not 0 <= selected < len(chapters):
        raise chapter.ExperimentError("Invalid chapter number")
    if selected + 1 >= len(chapters):
        raise chapter.ExperimentError("The selected chapter has no following readable EPUB section")
    current = chapters[selected]
    following = chapters[selected + 1]
    final_paragraph = current.text.rsplit("\n\n", 1)[-1]
    final_start = len(current.text) - len(final_paragraph)
    if not final_paragraph.strip():
        raise chapter.ExperimentError("The selected chapter has no final paragraph")
    remaining = chapter.BLOCK_TARGET - len(final_paragraph) - 2
    if remaining < 1:
        raise chapter.ExperimentError("The final paragraph leaves no room for real following text under the block target")
    following_text = take_following_prefix(following.text, min(FOLLOWING_CONTEXT_CHARS, remaining))
    plan = DiagnosticPlan(book, current.title, selected + 1, len(current.text), final_start,
                          final_paragraph, following.title, selected + 2, following_text)
    if any(len(value) > chapter.BLOCK_TARGET or len(value) > chapter.HARD_INPUT_LIMIT
           for value in (plan.test_a, plan.test_b)):
        raise chapter.ExperimentError("Diagnostic input exceeds the configured target or API input limit")
    return plan


def show_plan(epub: Path, plan: DiagnosticPlan, profile: dict) -> None:
    print(f"\nDiagnostic EPUB: {epub.name}")
    print(f"Book: {plan.book}")
    print(f"Model: {profile['model']} | Voice: {profile['voice']} | Speed: {profile['speed']}")
    print(f"Test A source: readable section [{plan.chapter_number}] {plan.chapter_title}, "
          f"extracted character offsets [{plan.final_paragraph_start}:{plan.chapter_chars})")
    print(f"Test A — final paragraph only: {len(plan.test_a)} characters")
    print("Exact Test A input begins:")
    print(plan.test_a)
    print("Exact Test A input ends.")
    print(f"Test B source: the same final paragraph, then readable section "
          f"[{plan.next_number}] {plan.next_title}, extracted character offsets "
          f"[0:{len(plan.following_text)})")
    print("The two real EPUB excerpts are separated by exactly two newline characters.")
    print(f"Test B — final paragraph + following EPUB text: {len(plan.test_b)} characters")
    print("Exact following EPUB text appended to Test B begins:")
    print(plan.following_text)
    print("Exact following EPUB text appended to Test B ends.")
    print("Estimated API requests: exactly 2")


def make_fidelity_instructions(profile: dict, baseline_instructions: str) -> str:
    if (profile["model"], profile["voice"], profile["speed"]) != ("gpt-4o-mini-tts", "cedar", 1.0):
        raise chapter.ExperimentError("Test C requires gpt-4o-mini-tts, cedar, and speed 1.0")
    combined = (baseline_instructions if all(sentence in baseline_instructions for sentence in FIDELITY_SENTENCES)
                else baseline_instructions + "\n\n" + FIDELITY_ADDENDUM)
    if len(combined) > chapter.HARD_INSTRUCTIONS_LIMIT:
        raise chapter.ExperimentError("Test C instructions exceed the API instructions limit")
    return combined


def show_fidelity_plan(epub: Path, plan: DiagnosticPlan, profile: dict, combined_instructions: str) -> None:
    print(f"\nTest C diagnostic EPUB: {epub.name}")
    print(f"Book: {plan.book} | Chapter: [{plan.chapter_number}] {plan.chapter_title}")
    print(f"Source: extracted chapter character offsets [{plan.final_paragraph_start}:{plan.chapter_chars})")
    print(f"Model: {profile['model']} | Voice: {profile['voice']} | Speed: {profile['speed']}")
    print(f"Test C input: {len(plan.test_a)} characters, identical to Test A")
    print("Exact Test C input begins:")
    print(plan.test_a)
    print("Exact Test C input ends.")
    print("Text Fidelity:")
    print(profile["text_fidelity"])
    print("Ending Fidelity:")
    print(profile["ending_fidelity"])
    print(f"Combined instructions: {len(combined_instructions)} characters")
    print("Estimated API requests: exactly 1 paid request")


def generate_fidelity(epub: Path, plan: DiagnosticPlan, profile: dict, combined_instructions: str) -> Path:
    from dotenv import load_dotenv
    from openai import OpenAI

    if len(plan.test_a) > chapter.BLOCK_TARGET or len(plan.test_a) > chapter.HARD_INPUT_LIMIT:
        raise chapter.ExperimentError("Test C input exceeds the configured target or API input limit")
    if not all(sentence in combined_instructions for sentence in FIDELITY_SENTENCES):
        raise chapter.ExperimentError("Test C fidelity instructions are missing")
    if len(combined_instructions) > chapter.HARD_INSTRUCTIONS_LIMIT:
        raise chapter.ExperimentError("Test C instructions exceed the API instructions limit")
    if (profile["model"], profile["voice"], profile["speed"]) != ("gpt-4o-mini-tts", "cedar", 1.0):
        raise chapter.ExperimentError("Test C requires gpt-4o-mini-tts, cedar, and speed 1.0")
    load_dotenv(dotenv_path=chapter.REPO_ROOT / "backend" / ".env", override=False)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise chapter.ExperimentError("OPENAI_API_KEY is not configured")
    if shutil.which("ffprobe") is None:
        raise chapter.ExperimentError("ffprobe must be available on PATH")
    client = OpenAI(api_key=key, max_retries=0)
    run_dir = (DIAGNOSTIC_OUTPUT / chapter.safe_name(plan.book) /
               chapter.safe_name(plan.chapter_title) /
               (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_test_c"))
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise chapter.ExperimentError(f"Cannot create diagnostic output directory: {run_dir}") from exc

    text_file = f"{TEST_C_STEM}.txt"
    instructions_file = f"{TEST_C_STEM}.instructions.txt"
    mp3_file = f"{TEST_C_STEM}.mp3"
    summary_file = run_dir / f"{TEST_C_STEM}.json"
    chapter.write_exact_text(run_dir / text_file, plan.test_a)
    chapter.write_exact_text(run_dir / instructions_file, combined_instructions)
    summary = {
        "status": "in_progress", "test": "C", "selected_epub": epub.name,
        "book": plan.book, "chapter": plan.chapter_title,
        "source_character_offsets": [plan.final_paragraph_start, plan.chapter_chars],
        "character_count": len(plan.test_a), "model": profile["model"],
        "voice": profile["voice"], "speed": profile["speed"],
        "text_file": text_file, "instructions_file": instructions_file,
        "mp3_file": mp3_file, "duration_seconds": None,
        "generation_time_seconds": None, "mp3_filesize_bytes": None,
        "planned_api_requests": 1,
    }
    chapter.write_json(summary_file, summary)
    audio_path = run_dir / mp3_file
    print(f"Generating Test C: {len(plan.test_a)} chars -> {mp3_file}")
    started = time.perf_counter()
    try:
        with client.audio.speech.with_streaming_response.create(
            model=profile["model"], voice=profile["voice"], speed=profile["speed"],
            input=plan.test_a, instructions=combined_instructions, response_format="mp3",
        ) as response:
            response.stream_to_file(audio_path)
        elapsed = time.perf_counter() - started
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            raise chapter.ExperimentError("OpenAI returned an empty MP3")
        duration = chapter.probe_duration(audio_path)
        summary.update(status="complete", duration_seconds=duration,
                       generation_time_seconds=elapsed, mp3_filesize_bytes=audio_path.stat().st_size)
        chapter.write_json(summary_file, summary)
    except Exception as exc:
        summary["status"] = "failed"
        chapter.write_json(summary_file, summary)
        raise chapter.ExperimentError(f"Test C failed ({type(exc).__name__}); files remain in {run_dir}") from exc
    print(f"Test C complete: {duration:.2f}s audio | {elapsed:.2f}s generation")
    print(f"MP3: {audio_path.name} | exact input: {text_file} | exact instructions: {instructions_file}")
    print(f"Metadata: {summary_file.name} | Output: {run_dir}")
    return run_dir


def generate(epub: Path, plan: DiagnosticPlan, profile: dict, instructions: str) -> Path:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(dotenv_path=chapter.REPO_ROOT / "backend" / ".env", override=False)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise chapter.ExperimentError("OPENAI_API_KEY is not configured")
    if shutil.which("ffprobe") is None:
        raise chapter.ExperimentError("ffprobe must be available on PATH")
    client = OpenAI(api_key=key, max_retries=0)
    run_dir = (DIAGNOSTIC_OUTPUT / chapter.safe_name(plan.book) /
               chapter.safe_name(plan.chapter_title) / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise chapter.ExperimentError(f"Cannot create diagnostic output directory: {run_dir}") from exc

    cases = (
        ("A", "test_a_final_paragraph", plan.test_a),
        ("B", "test_b_with_following", plan.test_b),
    )
    for _, stem, text in cases:
        chapter.write_exact_text(run_dir / f"{stem}.txt", text)
    summary = {
        "status": "in_progress", "selected_epub": epub.name, "book": plan.book,
        "chapter": plan.chapter_title, "model": profile["model"], "voice": profile["voice"],
        "speed": profile["speed"], "narration_profile": profile, "instructions": instructions,
        "source_boundaries": {
            "test_a_chapter": plan.chapter_title,
            "test_a_character_offsets": [plan.final_paragraph_start, plan.chapter_chars],
            "test_b_following_section": plan.next_title,
            "test_b_following_character_offsets": [0, len(plan.following_text)],
            "separator_between_sections": "\n\n",
        },
        "planned_api_requests": 2, "completed_api_requests": 0, "cases": [],
    }
    summary_path = run_dir / "diagnostic_summary.json"
    chapter.write_json(summary_path, summary)
    for label, stem, text in cases:
        audio_path = run_dir / f"{stem}.mp3"
        print(f"Generating Test {label}: {len(text)} chars -> {audio_path.name}")
        started = time.perf_counter()
        try:
            with client.audio.speech.with_streaming_response.create(
                model=profile["model"], voice=profile["voice"], speed=profile["speed"],
                input=text, instructions=instructions, response_format="mp3",
            ) as response:
                response.stream_to_file(audio_path)
            elapsed = time.perf_counter() - started
            if not audio_path.is_file() or audio_path.stat().st_size == 0:
                raise chapter.ExperimentError("OpenAI returned an empty MP3")
            duration = chapter.probe_duration(audio_path)
            summary["completed_api_requests"] += 1
            summary["cases"].append({
                "test": label, "characters": len(text), "duration_seconds": duration,
                "generation_time_seconds": elapsed, "mp3_file": audio_path.name,
                "text_file": f"{stem}.txt", "mp3_filesize_bytes": audio_path.stat().st_size,
            })
            chapter.write_json(summary_path, summary)
            print(f"  Success: duration {duration:.2f}s | generation {elapsed:.2f}s | "
                  f"MP3 {audio_path.name} | input {stem}.txt")
        except Exception as exc:
            summary["status"] = "failed"
            summary["failed_test"] = label
            chapter.write_json(summary_path, summary)
            raise chapter.ExperimentError(f"Test {label} failed ({type(exc).__name__}); completed files remain in {run_dir}") from exc
    summary["status"] = "complete"
    chapter.write_json(summary_path, summary)
    print(f"\nDiagnostic complete. Files: {run_dir}")
    for case in summary["cases"]:
        print(f"Test {case['test']}: {case['duration_seconds']:.2f}s audio | "
              f"{case['generation_time_seconds']:.2f}s generation | "
              f"{case['mp3_file']} | exact input {case['text_file']}")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, help="Use a specified EPUB instead of the native file picker")
    parser.add_argument("--test-c-fidelity", action="store_true",
                        help="Run one final-paragraph request with fidelity instructions; A/B mode is unchanged")
    args = parser.parse_args(argv)
    try:
        epub = args.epub or chapter.choose_epub()
        if epub is None:
            print("File selection cancelled. No API requests made.")
            return 0
        book, chapters = chapter.list_chapters(epub)
        print("Available chapters/sections:")
        for index, item in enumerate(chapters, 1):
            print(f"[{index}] {item.title}")
        selection = input("Enter chapter/section number to diagnose: ").strip()
        if not selection.isdecimal():
            raise chapter.ExperimentError("Invalid chapter number")
        plan = make_plan(book, chapters, int(selection) - 1)
        profile, instructions = chapter.load_profile()
        if args.test_c_fidelity:
            combined_instructions = make_fidelity_instructions(profile, instructions)
            show_fidelity_plan(epub, plan, profile, combined_instructions)
            answer = input("Proceed with exactly one paid API request? [Y/N] ").strip().lower()
            if answer != "y":
                print("Test C declined. No API requests made.")
                return 0
            generate_fidelity(epub, plan, profile, combined_instructions)
            return 0
        show_plan(epub, plan, profile)
        answer = input("Proceed with exactly two API requests? [Y/N] ").strip().lower()
        if answer != "y":
            print("Diagnostic declined. No API requests made.")
            return 0
        generate(epub, plan, profile, instructions)
        return 0
    except (chapter.ExperimentError, EOFError, KeyboardInterrupt) as exc:
        print(f"Diagnostic stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
