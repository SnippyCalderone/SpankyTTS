"""Local EPUB chapter-to-MP3 listening experiment; no production backend calls."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup, NavigableString, Tag


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROFILE_PATH = HERE / "narration_profile.json"
OUTPUT_ROOT = HERE / "output"
HARD_INPUT_LIMIT = 4096
BLOCK_TARGET = 3550
TAIL_PROTECTION_MAX_CHARS = 120
HARD_INSTRUCTIONS_LIMIT = 4096
EXCLUDED_TAGS = {"head", "script", "style", "nav", "svg", "math", "noscript"}
BLOCK_TAGS = {"p", "div", "section", "article", "blockquote", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
PROFILE_FIELDS = (
    "role", "voice_identity", "accent", "pace", "cadence", "emotional_range",
    "scene_dynamics", "intonation", "dialogue", "dialogue_tags", "interruptions",
    "tension", "humor", "punctuation", "consistency", "text_fidelity",
    "ending_fidelity", "whispering", "impression_performance_style", "avoid",
)


class ExperimentError(Exception):
    """An expected, user-facing experiment failure."""


@dataclass(frozen=True)
class Target:
    spine_index: int
    event_index: int
    title: str


@dataclass
class Document:
    path: str
    events: list[tuple[str, str]]
    anchors: dict[str, int]
    headings: list[tuple[str, int]]


@dataclass(frozen=True)
class Chapter:
    title: str
    text: str


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def normalize_zip_path(path: str) -> str:
    return posixpath.normpath(path.replace("\\", "/").lstrip("/"))


def resolve_href(base_path: str, href: str) -> tuple[str, str]:
    parsed = urlsplit(href)
    path = unquote(parsed.path)
    if not path:
        path = base_path
    else:
        path = posixpath.join(posixpath.dirname(base_path), path)
    return normalize_zip_path(path), unquote(parsed.fragment)


def read_member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise ExperimentError(f"EPUB member is missing: {name}") from exc


def find_package_path(archive: zipfile.ZipFile) -> str:
    try:
        root = ElementTree.fromstring(read_member(archive, "META-INF/container.xml"))
    except ElementTree.ParseError as exc:
        raise ExperimentError("EPUB container.xml cannot be parsed") from exc
    for element in root.iter():
        if local_name(element.tag) == "rootfile" and element.get("full-path"):
            return normalize_zip_path(element.attrib["full-path"])
    raise ExperimentError("EPUB has no OPF package path")


def parse_package(archive: zipfile.ZipFile, package_path: str):
    try:
        root = ElementTree.fromstring(read_member(archive, package_path))
    except ElementTree.ParseError as exc:
        raise ExperimentError("EPUB OPF package cannot be parsed") from exc
    manifest: dict[str, dict[str, str]] = {}
    spine: list[str] = []
    ncx_id = ""
    title = ""
    for element in root.iter():
        tag = local_name(element.tag)
        if tag == "item" and element.get("id"):
            manifest[element.attrib["id"]] = dict(element.attrib)
        elif tag == "spine":
            ncx_id = element.get("toc", "")
        elif tag == "itemref" and element.get("idref") and element.get("linear", "yes") != "no":
            spine.append(element.attrib["idref"])
        elif tag == "title" and not title and element.text:
            title = element.text.strip()
    return manifest, spine, ncx_id, title


def render_document(path: str, data: bytes) -> Document:
    soup = BeautifulSoup(data, "html.parser")
    root = soup.body or soup
    events: list[tuple[str, str]] = []
    anchors: dict[str, int] = {}
    headings: list[tuple[str, int]] = []

    def walk(node) -> None:
        if isinstance(node, NavigableString):
            events.append(("text", str(node)))
            return
        if not isinstance(node, Tag):
            return
        tag = node.name.lower() if node.name else ""
        if tag in EXCLUDED_TAGS:
            return
        if node.get("id"):
            anchors.setdefault(str(node["id"]), len(events))
        if node.get("name"):
            anchors.setdefault(str(node["name"]), len(events))
        if tag in {"h1", "h2"}:
            heading = node.get_text(" ", strip=True)
            if heading:
                headings.append((heading, len(events)))
        if tag == "br":
            events.append(("text", "\n"))
            return
        for child in node.children:
            walk(child)
        if tag in BLOCK_TAGS:
            events.append(("text", "\n\n"))

    walk(root)
    return Document(path=path, events=events, anchors=anchors, headings=headings)


def normalize_prose(raw: str) -> str:
    raw = raw.replace("\u00a0", " ")
    raw = re.sub(r"[^\S\n]+", " ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def extract_range(documents: list[Document], start: Target, end: Target | None) -> str:
    chunks = []
    last_spine = end.spine_index if end else len(documents) - 1
    for index in range(start.spine_index, last_spine + 1):
        doc = documents[index]
        begin = start.event_index if index == start.spine_index else 0
        finish = end.event_index if end and index == end.spine_index else len(doc.events)
        if finish > begin:
            chunk = normalize_prose("".join(value for _, value in doc.events[begin:finish]))
            if chunk:
                chunks.append(chunk)
    return "\n\n".join(chunks)


def navigation_targets(archive, manifest, package_path, ncx_id, documents):
    by_path = {doc.path: index for index, doc in enumerate(documents)}
    entries: list[tuple[str, str, str]] = []
    nav_item = next((item for item in manifest.values() if "nav" in item.get("properties", "").split()), None)
    if nav_item:
        nav_path, _ = resolve_href(package_path, nav_item["href"])
        try:
            soup = BeautifulSoup(read_member(archive, nav_path), "html.parser")
            nav = next((node for node in soup.find_all("nav") if "toc" in str(node.get("epub:type", "")).split() or node.get("role") == "doc-toc"), None)
            nav = nav or soup.find("nav")
            if nav:
                entries.extend((a.get_text(" ", strip=True), nav_path, a["href"]) for a in nav.find_all("a", href=True))
        except ExperimentError:
            pass
    if not entries and ncx_id in manifest:
        ncx_path, _ = resolve_href(package_path, manifest[ncx_id]["href"])
        try:
            root = ElementTree.fromstring(read_member(archive, ncx_path))
            for point in root.iter():
                if local_name(point.tag) != "navPoint":
                    continue
                label = next(("".join(child.itertext()).strip() for child in point if local_name(child.tag) == "navLabel"), "")
                href = next((child.get("src", "") for child in point if local_name(child.tag) == "content"), "")
                if label and href:
                    entries.append((label, ncx_path, href))
        except (ExperimentError, ElementTree.ParseError):
            pass
    targets = []
    for title, base, href in entries:
        path, fragment = resolve_href(base, href)
        if path not in by_path:
            continue
        spine_index = by_path[path]
        doc = documents[spine_index]
        if fragment and fragment not in doc.anchors:
            continue
        targets.append(Target(spine_index, doc.anchors.get(fragment, 0), title))
    return targets


def fallback_targets(documents: list[Document]) -> list[Target]:
    targets = []
    for index, doc in enumerate(documents):
        if doc.headings:
            first_title, first_position = doc.headings[0]
            if normalize_prose("".join(value for _, value in doc.events[:first_position])):
                targets.append(Target(index, 0, Path(doc.path).stem))
            for title, position in doc.headings:
                targets.append(Target(index, position, title))
        else:
            targets.append(Target(index, 0, Path(doc.path).stem))
    return targets


def list_chapters(epub_path: Path) -> tuple[str, list[Chapter]]:
    if epub_path.suffix.lower() != ".epub":
        raise ExperimentError("Selected file is not an .epub file")
    if not epub_path.is_file():
        raise ExperimentError(f"EPUB file does not exist: {epub_path}")
    try:
        with zipfile.ZipFile(epub_path) as archive:
            package_path = find_package_path(archive)
            manifest, spine, ncx_id, book_title = parse_package(archive, package_path)
            documents = []
            for item_id in spine:
                item = manifest.get(item_id)
                if not item or "nav" in item.get("properties", "").split():
                    continue
                path, _ = resolve_href(package_path, item.get("href", ""))
                media_type = item.get("media-type", "").lower()
                if media_type not in {"application/xhtml+xml", "text/html"} and not path.lower().endswith((".xhtml", ".html", ".htm")):
                    continue
                try:
                    documents.append(render_document(path, read_member(archive, path)))
                except ExperimentError:
                    continue
            if not documents:
                raise ExperimentError("EPUB spine has no readable HTML sections")
            targets = navigation_targets(archive, manifest, package_path, ncx_id, documents)
            if not targets:
                targets = fallback_targets(documents)
            # EPUB navigation may contain duplicate links and entries out of document order.
            targets.sort(key=lambda target: (target.spine_index, target.event_index))
            unique = []
            seen = set()
            for target in targets:
                position = (target.spine_index, target.event_index)
                if position not in seen:
                    unique.append(target)
                    seen.add(position)
            chapters = []
            for index, target in enumerate(unique):
                next_target = unique[index + 1] if index + 1 < len(unique) else None
                text = extract_range(documents, target, next_target)
                if text:
                    chapters.append(Chapter(target.title, text))
            if not chapters:
                raise ExperimentError("EPUB has no readable chapter text")
            return book_title or epub_path.stem, chapters
    except (zipfile.BadZipFile, OSError) as exc:
        raise ExperimentError("EPUB cannot be opened or parsed") from exc


def sentence_breaks(text: str, start: int, end: int) -> list[int]:
    results = []
    for match in re.finditer(r"[.!?]+[\"'”’)]*\s+", text[start:end]):
        position = start + match.end()
        prefix = text[start:start + match.start() + 1]
        word = re.search(r"([A-Za-z]+)\.$", prefix)
        if word and word.group(1).lower() in {"mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vs"}:
            continue
        results.append(position)
    return results


def plan_blocks(text: str, target: int = BLOCK_TARGET) -> list[str]:
    if not text.strip():
        raise ExperimentError("Selected chapter has no readable text")
    if not 1 <= target < HARD_INPUT_LIMIT:
        raise ExperimentError("Block target must be below the API input limit")
    blocks = []
    start = 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            paragraph = [m.end() + start for m in re.finditer(r"\n\n", text[start:end])]
            sentence = sentence_breaks(text, start, end)
            words = [m.end() + start for m in re.finditer(r"\s+", text[start:end])]
            minimum = start + int(target * 0.55)
            boundary = next((points[-1] for points in (paragraph, sentence, words) if points and points[-1] >= minimum), None)
            if boundary is None:
                boundary = words[-1] if words else None
            if boundary is None or boundary <= start:
                raise ExperimentError("A word exceeds the planned block limit")
            end = boundary
            # A short paragraph at the end of a non-final block is easy for
            # narration to omit. Cut at the preceding paragraph boundary and
            # let the next loop replan from that exact source position.
            if text[start:end].endswith("\n\n"):
                previous_separator = text.rfind("\n\n", start, end - 2)
                if previous_separator >= start:
                    earlier_boundary = previous_separator + 2
                    tail = text[earlier_boundary:end - 2]
                    if earlier_boundary >= minimum and 0 < len(tail.strip()) <= TAIL_PROTECTION_MAX_CHARS:
                        end = earlier_boundary
        blocks.append(text[start:end])
        start = end
    if "".join(blocks) != text or any(len(block) > target or len(block) > HARD_INPUT_LIMIT for block in blocks):
        raise ExperimentError("Block planning lost text or exceeded the target")
    return blocks


def load_profile(path: Path = PROFILE_PATH) -> tuple[dict, str]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"Cannot read narration profile: {path}") from exc
    for key in ("model", "voice", *PROFILE_FIELDS):
        if key not in profile:
            raise ExperimentError(f"Narration profile is missing {key}")
    if not isinstance(profile["model"], str) or not profile["model"].strip():
        raise ExperimentError("Profile model must be a nonempty string")
    if not isinstance(profile["voice"], str) or not profile["voice"].strip():
        raise ExperimentError("Profile voice must be a nonempty string")
    speed = profile.get("speed")
    if isinstance(speed, bool) or not isinstance(speed, (float, int)) or not 0.25 <= speed <= 4.0:
        raise ExperimentError("Profile speed must be between 0.25 and 4.0")
    lines = []
    for key in PROFILE_FIELDS:
        value = profile[key]
        if key == "avoid":
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ExperimentError("Profile avoid must be a list of nonempty strings")
            value = "; ".join(value)
        elif not isinstance(value, str) or not value.strip():
            raise ExperimentError(f"Profile {key} must be a nonempty string")
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    instructions = "\n".join(lines)
    if len(instructions) > HARD_INSTRUCTIONS_LIMIT:
        raise ExperimentError(f"Narration instructions exceed {HARD_INSTRUCTIONS_LIMIT} characters")
    return profile, instructions


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)[:80].rstrip(" .") or "untitled"
    if cleaned.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        cleaned = f"_{cleaned}"
    return cleaned


def write_exact_text(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def concatenate_mp3(parts: list[Path], destination: Path) -> None:
    # The concat demuxer requires an input list; keep it next to the generated parts.
    list_path = destination.with_name("ffmpeg_concat_list.txt")
    lines = []
    for part in parts:
        # Files are local safe_name-derived paths; use absolute paths and escape apostrophes.
        quoted = part.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{quoted}'")
    write_exact_text(list_path, "\n".join(lines) + "\n")
    try:
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(destination)],
            check=True, capture_output=True, text=True,
        )
    finally:
        list_path.unlink(missing_ok=True)


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(round(seconds), 60)
    return f"{minutes}m {remainder:02d}s"


def show_plan(epub: Path, chapter: Chapter, blocks: list[str], profile: dict) -> None:
    print(f"\nSelected EPUB: {epub.name}")
    print(f"Selected chapter: {chapter.title}")
    print(f"Characters: {len(chapter.text):,}")
    print(f"Words: {len(chapter.text.split()):,}")
    print(f"Maximum TTS input: {HARD_INPUT_LIMIT} characters")
    print(f"Target block size: {BLOCK_TARGET} characters")
    print(f"Model: {profile['model']} | Voice: {profile['voice']} | Speed: {profile['speed']}")
    print(f"Planned narration blocks: {len(blocks)}")
    print("Block plan:")
    for index, block in enumerate(blocks, 1):
        print(f"  Part {index}: {len(block):,} chars")
    print(f"Estimated requests: {len(blocks)}")


def generate(epub: Path, book: str, chapter: Chapter, blocks: list[str], profile: dict, instructions: str) -> Path:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(dotenv_path=REPO_ROOT / "backend" / ".env", override=False)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ExperimentError("OPENAI_API_KEY is not configured")
    if shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None:
        raise ExperimentError("ffprobe and ffmpeg must be available on PATH")
    client = OpenAI(api_key=key, max_retries=0)
    run_dir = OUTPUT_ROOT / safe_name(book) / safe_name(chapter.title) / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ExperimentError(f"Cannot create output directory: {run_dir}") from exc
    write_exact_text(run_dir / "chapter_source.txt", chapter.text)
    for index, block in enumerate(blocks, 1):
        write_exact_text(run_dir / f"part_{index:03d}.txt", block)
    summary = {
        "status": "in_progress", "selected_epub": epub.name, "book": book, "chapter": chapter.title,
        "model": profile["model"], "voice": profile["voice"], "speed": profile["speed"],
        "narration_profile": profile, "instructions": instructions,
        "source_character_count": len(chapter.text), "source_word_count": len(chapter.text.split()),
        "number_of_blocks": len(blocks), "characters_per_block": [len(block) for block in blocks],
        "parts": [], "total_audio_duration_seconds": 0.0, "total_wall_time_seconds": 0.0,
        "total_api_generation_seconds": 0.0, "total_mp3_filesize_bytes": 0,
    }
    summary_path = run_dir / "run_summary.json"
    write_json(summary_path, summary)
    started = time.perf_counter()
    completed = []
    for index, block in enumerate(blocks, 1):
        filename = f"part_{index:03d}.mp3"
        output_path = run_dir / filename
        print(f"Generating part {index}/{len(blocks)}... chars={len(block):,} file={filename}")
        part_started = time.perf_counter()
        try:
            with client.audio.speech.with_streaming_response.create(
                model=profile["model"], voice=profile["voice"], speed=profile["speed"],
                input=block, instructions=instructions, response_format="mp3",
            ) as response:
                response.stream_to_file(output_path)
            elapsed = time.perf_counter() - part_started
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise ExperimentError("OpenAI returned an empty MP3")
            duration = probe_duration(output_path)
            size = output_path.stat().st_size
            completed.append(output_path)
            summary["parts"].append({
                "part": index, "characters": len(block), "words": len(block.split()),
                "duration_seconds": duration, "generation_time_seconds": elapsed,
                "filesize_bytes": size, "file": filename, "text_file": f"part_{index:03d}.txt",
            })
            summary["total_audio_duration_seconds"] += duration
            summary["total_api_generation_seconds"] += elapsed
            summary["total_mp3_filesize_bytes"] += size
            summary["total_wall_time_seconds"] = time.perf_counter() - started
            write_json(summary_path, summary)
            print(f"  Success: {filename} | API {elapsed:.1f}s | audio {format_duration(duration)} | {size:,} bytes")
        except Exception as exc:
            summary["status"] = "failed"
            summary["failed_part"] = index
            summary["total_wall_time_seconds"] = time.perf_counter() - started
            write_json(summary_path, summary)
            print(f"  Failed: part {index}/{len(blocks)} after {time.perf_counter() - part_started:.1f}s ({type(exc).__name__})", file=sys.stderr)
            print(f"  Completed MP3 parts remain in: {run_dir}", file=sys.stderr)
            raise ExperimentError(f"Part {index} failed; completed parts remain in {run_dir}") from exc
    combined = run_dir / "chapter_complete.mp3"
    try:
        concatenate_mp3(completed, combined)
        summary["combined_file"] = combined.name
        summary["combined_duration_seconds"] = probe_duration(combined)
        print(f"Combined MP3: {combined.name} ({format_duration(summary['combined_duration_seconds'])})")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        summary["concatenation_error"] = type(exc).__name__
        combined.unlink(missing_ok=True)
        print("FFmpeg concatenation failed; individual MP3 parts were preserved.")
    summary["status"] = "complete"
    summary["total_wall_time_seconds"] = time.perf_counter() - started
    summary["average_characters_per_part"] = sum(len(block) for block in blocks) / len(blocks)
    summary["average_audio_duration_seconds"] = summary["total_audio_duration_seconds"] / len(blocks)
    audio_seconds = summary["total_audio_duration_seconds"]
    summary["characters_per_minute"] = len(chapter.text) * 60 / audio_seconds if audio_seconds else None
    summary["approximate_words_per_minute"] = len(chapter.text.split()) * 60 / audio_seconds if audio_seconds else None
    write_json(summary_path, summary)
    print(f"\nGeneration complete: {book} — {chapter.title}")
    print(f"Parts: {len(completed)} | source: {len(chapter.text):,} chars / {len(chapter.text.split()):,} words")
    for part in summary["parts"]:
        print(f"  Part {part['part']}: {part['characters']:,} chars | {format_duration(part['duration_seconds'])} | {part['generation_time_seconds']:.1f}s | {part['filesize_bytes']:,} bytes | {part['file']}")
    print(f"Total audio: {format_duration(summary['total_audio_duration_seconds'])} | API time: {summary['total_api_generation_seconds']:.1f}s | wall time: {summary['total_wall_time_seconds']:.1f}s")
    print(f"Average: {summary['average_characters_per_part']:.0f} chars/part | {format_duration(summary['average_audio_duration_seconds'])}/part")
    if summary["characters_per_minute"] is not None:
        print(f"Narration rate: {summary['characters_per_minute']:.0f} chars/min | {summary['approximate_words_per_minute']:.0f} words/min")
    print(f"Total part MP3 size: {summary['total_mp3_filesize_bytes']:,} bytes | requests: {len(completed)}")
    print(f"Output: {run_dir}")
    return run_dir


def choose_epub() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        selection = filedialog.askopenfilename(title="Select an EPUB", filetypes=[("EPUB books", "*.epub")])
    finally:
        root.destroy()
    return Path(selection) if selection else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epub", type=Path, help="Use a specified EPUB instead of the native file picker (for local tests)")
    args = parser.parse_args(argv)
    try:
        epub = args.epub or choose_epub()
        if epub is None:
            print("File selection cancelled. No API requests made.")
            return 0
        book, chapters = list_chapters(epub)
        print("Available chapters:")
        for index, chapter in enumerate(chapters, 1):
            print(f"[{index}] {chapter.title}")
        selection = input("Enter chapter number: ").strip()
        if not selection.isdecimal() or not 1 <= int(selection) <= len(chapters):
            raise ExperimentError("Invalid chapter number")
        chapter = chapters[int(selection) - 1]
        blocks = plan_blocks(chapter.text)
        profile, instructions = load_profile()
        show_plan(epub, chapter, blocks, profile)
        answer = input("Proceed with generation? [Y/N] ").strip().lower()
        if answer != "y":
            print("Generation declined. No API requests made.")
            return 0
        generate(epub, book, chapter, blocks, profile, instructions)
        return 0
    except (ExperimentError, EOFError, KeyboardInterrupt) as exc:
        print(f"Experiment stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
