"""Build listening aids from the saved Phase 2B.2B-1 alignment; never rerun ASR."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

from run import OUTPUT_ROOT, fixture_file, save_json, sha256, validate_fixture


CONTEXT_CHARS = 80
CONTEXT_WORDS = 5
PADDING_MS = 2000
ENDPOINT_WINDOW_MS = 6000


def seconds(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.3f}"


def shown(value: str) -> str:
    return value.replace("\r", "\\r").replace("\n", "\\n")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "region"


def reason(operations: list[dict], kind: str) -> str:
    if kind == "beginning":
        return "ASR recognizes the first source word, but a human must hear whether its onset is complete. Preceding chapter text belongs to the prior block and should not leak into this audio."
    if kind == "end":
        return "ASR recognizes the final source word, but a human must hear whether its ending is complete. Following chapter text belongs to the next block and should not appear here."
    if any(op["timing_issue"] for op in operations):
        return "The ASR word has start == end. Its lexical text matches, but this stamp cannot support a source-to-audio boundary."
    if any(op["ambiguous"] for op in operations):
        return "The source compound aligns ambiguously to an ASR addition plus a conflicting token; the recognizer may have split or misheard it."
    if all(op["source_text"].lower() == "stephano" for op in operations):
        return "Source spelling Stephano differs from ASR Stefano; sound cannot establish the printed spelling."
    return "ASR and source use different words; listening is needed to separate a recognition error from a spoken TTS deviation."


def source_context(source: str, start: int, end: int) -> str:
    left = shown(source[max(0, start - CONTEXT_CHARS):start])
    middle = shown(source[start:end])
    right = shown(source[end:min(len(source), end + CONTEXT_CHARS)])
    return f"{left}⟦{middle}⟧{right}"


def asr_context(words: list[dict], start: int, end: int) -> str:
    left = "".join(row["text"] for row in words[max(0, start - CONTEXT_WORDS):start]).strip()
    middle = "".join(row["text"] for row in words[start:end]).strip()
    right = "".join(row["text"] for row in words[end:min(len(words), end + CONTEXT_WORDS)]).strip()
    return f"{left} ⟦{middle}⟧ {right}".strip()


def clip_expected_source(operations: list[dict], source: str, start_ms: int, end_ms: int) -> dict:
    """Give the reader source text covered by a review window, not a slice map."""
    covered = [op for op in operations
               if op["source_token_end"] > op["source_token_start"]
               and op["observed_asr_start_ms"] is not None
               and op["observed_asr_end_ms"] is not None
               and op["observed_asr_start_ms"] < end_ms
               and op["observed_asr_end_ms"] >= start_ms]
    if not covered:
        raise ValueError(f"No source text near review window {start_ms}-{end_ms}")
    start = min(op["block_start"] for op in covered)
    end = max(op["block_end"] for op in covered)
    return {"block_start": start, "block_end": end,
            "text": source[start:end]}


def zero_duration_evidence(raw: dict, target: str) -> dict:
    words = raw["words"]
    candidates = [row for row in words if row["text"].strip(" ,.!?\"'").lower() == target.lower()
                  and row["start_ms"] == row["end_ms"]]
    if len(candidates) != 1:
        raise ValueError(f"Expected one zero-duration {target!r}; found {len(candidates)}")
    word = candidates[0]
    index = word["index"]
    segment = next((seg for seg in raw["segments"]
                    if any(row["index"] == index for row in seg["words"])), None)
    if segment is None:
        raise ValueError(f"Missing segment for ASR word {index}")
    previous, following = words[index - 1], words[index + 1]
    return {
        "word": word, "previous_word": previous, "next_word": following,
        "gap_from_previous_end_ms": word["start_ms"] - previous["end_ms"],
        "gap_to_next_start_ms": following["start_ms"] - word["end_ms"],
        "segment_start_ms": segment["start_ms"], "segment_end_ms": segment["end_ms"],
        "segment_text": segment["text"],
        "segment_avg_logprob": segment["avg_logprob"],
        "segment_no_speech_prob": segment["no_speech_prob"],
        "assessment": "Likely faster-whisper word-timestamp artifact: the word is in the segment transcript with high ASR probability, but it has no positive-duration interval and the next word starts at the same time. Listening must confirm actual speech. No corrected timestamp is assigned.",
    }


def create_review() -> None:
    manifest, source, audio_path, duration_ms = validate_fixture()
    output = OUTPUT_ROOT / manifest["id"]
    raw_path = output / "raw_asr.json"
    alignment_path = output / "alignment.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    if (alignment["source_text"] != source or alignment["fixture"] != manifest
            or alignment["raw_asr_sha256"] != sha256(raw_path)
            or raw["audio_sha256"] != manifest["audio_sha256"]
            or alignment["model"] != raw["model"]):
        raise ValueError("Saved ASR, alignment, and authoritative fixture do not agree")
    chapter_path = fixture_file(manifest["chapter_source_file"], manifest["chapter_source_sha256"])
    chapter = chapter_path.read_text(encoding="utf-8")
    operations = alignment["operations"]
    flagged = [(index, op) for index, op in enumerate(operations)
               if op["status"] not in {"exact", "normalized"}]
    if not flagged:
        raise ValueError("No flagged operations to review")

    groups: list[list[tuple[int, dict]]] = []
    for index, op in flagged:
        if (groups and len(groups[-1]) == 1
                and groups[-1][0][1]["status"] == "addition"
                and op["ambiguous"]
                and groups[-1][0][1]["block_start"] == op["block_start"]
                and groups[-1][0][1]["asr_word_end"] == op["asr_word_start"]):
            groups[-1].append((index, op))
        else:
            groups.append([(index, op)])

    specs = []
    first, last = operations[0], operations[-1]
    specs.append(("beginning", "beginning_Finally", [first], [0]))
    for group in groups:
        indices = [index for index, _ in group]
        ops = [op for _, op in group]
        label = "blue_gray" if len(group) > 1 else slug(ops[0]["source_text"] or ops[0]["asr_text"])
        specs.append(("discrepancy", label, ops, indices))
    specs.append(("end", "end_you", [last], [len(operations) - 1]))
    specs.sort(key=lambda item: min(op["observed_asr_start_ms"] for op in item[2]))

    review_root = output / "review"
    clips_dir = review_root / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for number, (kind, label, ops, indices) in enumerate(specs, 1):
        block_start = min(op["block_start"] for op in ops)
        block_end = max(op["block_end"] for op in ops)
        asr_start = min(op["asr_word_start"] for op in ops)
        asr_end = max(op["asr_word_end"] for op in ops)
        observed_start = min(op["observed_asr_start_ms"] for op in ops)
        observed_end = max(op["observed_asr_end_ms"] for op in ops)
        if kind == "beginning":
            clip_start, clip_end = 0, min(duration_ms, ENDPOINT_WINDOW_MS)
        elif kind == "end":
            clip_start, clip_end = max(0, duration_ms - ENDPOINT_WINDOW_MS), duration_ms
        else:
            clip_start = max(0, observed_start - PADDING_MS)
            clip_end = min(duration_ms, observed_end + PADDING_MS)
        filename = f"{number:03d}_{label}_{seconds(clip_start)}s-{seconds(clip_end)}s.wav"
        clip_path = clips_dir / filename
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(audio_path), "-ss", seconds(clip_start),
            "-t", seconds(clip_end - clip_start), "-ac", "1", "-ar", "24000",
            "-c:a", "pcm_s16le", str(clip_path),
        ], check=True)
        expected = clip_expected_source(operations, source, clip_start, clip_end)
        row = {
            "number": number, "kind": kind, "label": label,
            "operation_indices": indices,
            "block_start": block_start, "block_end": block_end,
            "chapter_start": manifest["chapter_source_start"] + block_start,
            "chapter_end": manifest["chapter_source_start"] + block_end,
            "authoritative_source_text": source[block_start:block_end],
            "asr_text": "".join(word["text"] for word in raw["words"][asr_start:asr_end]).strip(),
            "asr_word_start": asr_start, "asr_word_end": asr_end,
            "audio_start_ms": ops[0]["audio_start_ms"] if len(ops) == 1 else None,
            "audio_end_ms": ops[0]["audio_end_ms"] if len(ops) == 1 else None,
            "observed_asr_start_ms": observed_start,
            "observed_asr_end_ms": observed_end,
            "classification": "+".join(dict.fromkeys(op["status"] for op in ops)),
            "lexical_relation": "+".join(dict.fromkeys(op["lexical_relation"] for op in ops)),
            "source_context": source_context(source, block_start, block_end),
            "asr_context": asr_context(raw["words"], asr_start, asr_end),
            "reason_uncertain": reason(ops, kind),
            "clip_start_ms": clip_start, "clip_end_ms": clip_end,
            "clip_file": "clips/" + filename,
            "expected_source_in_clip_approximate": expected,
        }
        if kind == "beginning":
            row["adjacent_chapter_source_outside_block"] = {
                "before": shown(chapter[max(0, manifest["chapter_source_start"] - 100):manifest["chapter_source_start"]]),
                "after": None,
            }
        elif kind == "end":
            row["adjacent_chapter_source_outside_block"] = {
                "before": None,
                "after": shown(chapter[manifest["chapter_source_end"]:manifest["chapter_source_end"] + 100]),
            }
        rows.append(row)

    covered_indices = [index for row in rows if row["kind"] == "discrepancy"
                       for index in row["operation_indices"]]
    if sorted(covered_indices) != sorted(index for index, _ in flagged):
        raise AssertionError("Review entries do not cover every flagged operation exactly once")
    zero_evidence = [zero_duration_evidence(raw, target) for target in ("staring", "Uncle")]
    review = {
        "fixture_id": manifest["id"],
        "source_sha256": manifest["source_sha256"],
        "audio_sha256": manifest["audio_sha256"],
        "raw_asr_sha256": sha256(raw_path),
        "alignment_sha256": sha256(alignment_path),
        "note": "Clips and expected source coverage are listening aids, never production slice boundaries. ASR times remain uncorrected.",
        "flagged_operation_count": len(flagged),
        "discrepancy_region_count": len(groups),
        "endpoint_region_count": 2,
        "review_region_count": len(rows),
        "regions": rows,
        "zero_duration_evidence": zero_evidence,
    }
    save_json(review_root / "review_manifest.json", review)
    markdown = [
        "# part_002 human listening review",
        "",
        f"Fixture: `{manifest['id']}`. Source offsets are half-open Python Unicode character ranges; chapter offsets refer to the saved `chapter_source.txt`.",
        f"Saved ASR and alignment: `{sha256(raw_path)}` / `{sha256(alignment_path)}` SHA-256.",
        f"{len(groups)} discrepancy regions cover all {len(flagged)} flagged operations; two endpoint checks make {len(rows)} review windows.",
        "", "**Status remains ALIGNED_BUT_UNCERTAIN.** These clips are listening aids only. Their edges are not source/audio boundaries for cached playback. No human listening judgment is recorded here.",
        "", "For each clip, compare the expected source passage with what is heard. Mark any actual spoken difference, clipped word, missing word, or unreliable timing before changing verification status.",
    ]
    for row in rows:
        markdown += [
            "", f"## {row['number']:03d} — {row['label']}", "",
            f"- Clip: [{row['clip_file']}]({row['clip_file']}) ({seconds(row['clip_start_ms'])}–{seconds(row['clip_end_ms'])} s)",
            f"- Focus: chapter `[{row['chapter_start']}, {row['chapter_end']})`, block `[{row['block_start']}, {row['block_end']})`",
            f"- Source: `{shown(row['authoritative_source_text'])}`; ASR: `{shown(row['asr_text'])}`",
            f"- ASR observed time: {seconds(row['observed_asr_start_ms'])}–{seconds(row['observed_asr_end_ms'])} s; mapped audio time: " + (f"{seconds(row['audio_start_ms'])}–{seconds(row['audio_end_ms'])} s" if row['audio_start_ms'] is not None else "none"),
            f"- Current classification: `{row['classification']}` (`{row['lexical_relation']}`)",
            f"- Uncertainty: {row['reason_uncertain']}",
            f"- Surrounding source: {row['source_context']}",
            f"- Surrounding ASR: {row['asr_context']}",
            f"- Expected source within clip (approximate, based on ASR timestamps): `{shown(row['expected_source_in_clip_approximate']['text'])}`",
        ]
        if "adjacent_chapter_source_outside_block" in row:
            adjacent = row["adjacent_chapter_source_outside_block"]
            side = "before" if row["kind"] == "beginning" else "after"
            markdown += [f"- Adjacent chapter text {side} this block: `{adjacent[side]}`. This belongs to the neighboring block; use it to check for boundary leakage."]
    markdown += ["", "## Zero-duration word evidence", ""]
    for item in zero_evidence:
        word, previous, following = item["word"], item["previous_word"], item["next_word"]
        markdown += [
            f"- **{word['text'].strip()}** (ASR #{word['index']}): {seconds(word['start_ms'])}–{seconds(word['end_ms'])} s, probability {word['probability']:.4f}. Previous `{previous['text'].strip()}` {seconds(previous['start_ms'])}–{seconds(previous['end_ms'])} s; next `{following['text'].strip()}` {seconds(following['start_ms'])}–{seconds(following['end_ms'])} s. Gap after previous: {item['gap_from_previous_end_ms']} ms; gap before next: {item['gap_to_next_start_ms']} ms. Segment {seconds(item['segment_start_ms'])}–{seconds(item['segment_end_ms'])} s: `{item['segment_text'].strip()}`. {item['assessment']}",
        ]
    (review_root / "review.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(f"Review: {review_root / 'review.md'}")
    print(f"Flagged operations: {len(flagged)}; discrepancy regions: {len(groups)}; total windows/clips: {len(rows)}")


if __name__ == "__main__":
    create_review()
