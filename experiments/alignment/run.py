"""Run the local, read-only Chapter Five alignment proof or query its result."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time

from core import AsrWord, build_alignment, lookup


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = EXPERIMENT_ROOT / "fixture.json"
MODEL_CACHE = EXPERIMENT_ROOT / ".models"
OUTPUT_ROOT = EXPERIMENT_ROOT / "output"
MODEL_NAME = "small.en"
MODEL_REPO = "Systran/faster-whisper-small.en"
MODEL_REVISION = "d1d751a5f8271d482d14ca55d9e2deeebbae577f"
MODEL_BIN_SHA256 = "62b2a45b05ee59acb4a5341b33ee35e041395d378d418a18acfe4c9e768ee37a"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_file(relative: str, expected_hash: str) -> Path:
    path = (REPO_ROOT / relative).resolve()
    if not path.is_relative_to(REPO_ROOT) or not path.is_file():
        raise ValueError(f"Fixture file is missing or outside the repository: {relative}")
    if sha256(path) != expected_hash:
        raise ValueError(f"Fixture SHA-256 differs from manifest: {relative}")
    return path


def probe_duration_ms(path: Path) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        check=True, capture_output=True, text=True)
    return round(float(result.stdout.strip()) * 1000)


def validate_fixture() -> tuple[dict, str, Path, int]:
    manifest = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    source_path = fixture_file(manifest["source_file"], manifest["source_sha256"])
    audio_path = fixture_file(manifest["audio_file"], manifest["audio_sha256"])
    chapter_path = fixture_file(manifest["chapter_source_file"], manifest["chapter_source_sha256"])
    summary_path = fixture_file(manifest["run_summary_file"], manifest["run_summary_sha256"])
    source = source_path.read_text(encoding="utf-8")
    chapter = chapter_path.read_text(encoding="utf-8")
    start, end = manifest["chapter_source_start"], manifest["chapter_source_end"]
    if (len(source) != manifest["source_character_count"] or
            len(source.split()) != manifest["source_whitespace_word_count"] or
            end - start != len(source) or chapter[start:end] != source):
        raise ValueError("Saved block text does not match the declared chapter source span")
    run_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    part = run_summary["parts"][manifest["part"] - 1]
    if (run_summary["status"] != "complete" or part["text_file"] != source_path.name or
            part["file"] != audio_path.name or part["characters"] != len(source) or
            run_summary["model"] != manifest["generation_model"] or
            run_summary["voice"] != manifest["generation_voice"] or
            run_summary["speed"] != manifest["generation_speed"]):
        raise ValueError("Run summary does not identify this fixture and its generation settings")
    duration_ms = probe_duration_ms(audio_path)
    if abs(duration_ms - round(manifest["audio_duration_seconds"] * 1000)) > 1:
        raise ValueError("Audio duration differs from manifest")
    return manifest, source, audio_path, duration_ms


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def download_approved_model() -> None:
    from faster_whisper.utils import download_model
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    snapshot = download_model(MODEL_NAME, cache_dir=str(MODEL_CACHE),
                              revision=MODEL_REVISION, use_auth_token=False)
    if sha256(Path(snapshot) / "model.bin") != MODEL_BIN_SHA256:
        raise ValueError("Downloaded model weights differ from the approved model identity")
    print(f"{MODEL_REPO} snapshot: {snapshot}")


def run_proof() -> None:
    manifest, source, audio_path, duration_ms = validate_fixture()
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model

    # The explicitly approved weights have been downloaded once. Every proof
    # run after that resolves the model locally and makes no network request.
    snapshot = Path(download_model(MODEL_NAME, cache_dir=str(MODEL_CACHE),
                                   revision=MODEL_REVISION, local_files_only=True,
                                   use_auth_token=False))
    if snapshot.name != MODEL_REVISION or sha256(snapshot / "model.bin") != MODEL_BIN_SHA256:
        raise ValueError("Local model snapshot differs from the recorded model identity")
    model_identity = {
        "model_name": MODEL_NAME, "model_repo": MODEL_REPO,
        "snapshot_revision": snapshot.name,
        "model_bin_sha256": sha256(snapshot / "model.bin"),
        "config_sha256": sha256(snapshot / "config.json"),
        "tokenizer_sha256": sha256(snapshot / "tokenizer.json"),
        "faster_whisper_version": importlib.metadata.version("faster-whisper"),
        "ctranslate2_version": importlib.metadata.version("ctranslate2"),
        "python_version": sys.version.split()[0],
        "device": "cpu", "compute_type": "int8", "language": "en",
        "word_timestamps": True, "vad_filter": False,
        "condition_on_previous_text": False, "beam_size": 5,
    }
    started = time.perf_counter()
    model = WhisperModel(str(snapshot), device="cpu", compute_type="int8",
                         local_files_only=True)
    loaded = time.perf_counter()
    segments_iter, info = model.transcribe(
        str(audio_path), language="en", word_timestamps=True, beam_size=5,
        vad_filter=False, condition_on_previous_text=False)
    segments = list(segments_iter)
    transcribed = time.perf_counter()

    words = []
    raw_segments = []
    for segment in segments:
        raw_words = []
        for word in segment.words or []:
            row = {"index": len(words), "text": word.word,
                   "start_ms": round(word.start * 1000),
                   "end_ms": round(word.end * 1000),
                   "probability": word.probability}
            words.append(AsrWord(**row))
            raw_words.append(row)
        raw_segments.append({"start_ms": round(segment.start * 1000),
                             "end_ms": round(segment.end * 1000),
                             "text": segment.text, "words": raw_words,
                             "avg_logprob": segment.avg_logprob,
                             "no_speech_prob": segment.no_speech_prob})
    raw_asr = {
        "audio_file": manifest["audio_file"], "audio_sha256": manifest["audio_sha256"],
        "model": model_identity,
        "runtime_seconds": {"model_load": round(loaded - started, 3),
                            "transcription": round(transcribed - loaded, 3),
                            "total": round(transcribed - started, 3)},
        "language_detected": info.language,
        "language_probability": info.language_probability,
        "segments": raw_segments,
        "words": [dict(index=word.index, text=word.text, start_ms=word.start_ms,
                       end_ms=word.end_ms, probability=word.probability)
                  for word in words],
    }
    output = OUTPUT_ROOT / manifest["id"]
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "raw_asr.json", raw_asr)

    artifact = build_alignment(source, words, manifest["chapter_source_start"], duration_ms)
    artifact["fixture"] = manifest
    artifact["model"] = model_identity
    artifact["raw_asr_sha256"] = sha256(output / "raw_asr.json")
    artifact["runtime_seconds"] = raw_asr["runtime_seconds"]
    save_json(output / "alignment.json", artifact)
    save_json(output / "model_identity.json", model_identity)
    frozen = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True,
                            capture_output=True, text=True)
    (output / "requirements_resolved.txt").write_text(frozen.stdout, encoding="utf-8")

    print(f"Output: {output}")
    print(f"ASR runtime: {raw_asr['runtime_seconds']['transcription']:.3f}s "
          f"(model load {raw_asr['runtime_seconds']['model_load']:.3f}s)")
    print(json.dumps(artifact["summary"], ensure_ascii=False, indent=2))


def reconcile_saved() -> None:
    """Rebuild the map deterministically from the saved raw ASR, without ASR."""
    manifest, source, _, duration_ms = validate_fixture()
    output = OUTPUT_ROOT / manifest["id"]
    raw_path = output / "raw_asr.json"
    raw_asr = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw_asr["audio_sha256"] != manifest["audio_sha256"] or raw_asr["model"]["model_name"] != MODEL_NAME:
        raise ValueError("Saved raw ASR does not identify the approved fixture and model")
    words = [AsrWord(**row) for row in raw_asr["words"]]
    artifact = build_alignment(source, words, manifest["chapter_source_start"], duration_ms)
    artifact["fixture"] = manifest
    artifact["model"] = raw_asr["model"]
    artifact["raw_asr_sha256"] = sha256(raw_path)
    artifact["runtime_seconds"] = raw_asr["runtime_seconds"]
    save_json(output / "alignment.json", artifact)
    print(json.dumps(artifact["summary"], ensure_ascii=False, indent=2))


def query(start: int, end: int, coordinate: str) -> None:
    manifest = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    artifact_path = OUTPUT_ROOT / manifest["id"] / "alignment.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    print(json.dumps(lookup(artifact, start, end, coordinate), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("download-model", help="Download the approved small.en weights locally")
    subparsers.add_parser("run", help="Run local ASR and reconcile the fixed fixture")
    subparsers.add_parser("reconcile", help="Rebuild mapping from saved raw ASR without retranscribing")
    lookup_parser = subparsers.add_parser("lookup", help="Look up a saved source range")
    lookup_parser.add_argument("start", type=int)
    lookup_parser.add_argument("end", type=int)
    lookup_parser.add_argument("--coordinate", choices=["chapter", "block"], default="chapter")
    args = parser.parse_args()
    if args.action == "download-model":
        download_approved_model()
    elif args.action == "run":
        run_proof()
    elif args.action == "reconcile":
        reconcile_saved()
    else:
        query(args.start, args.end, args.coordinate)


if __name__ == "__main__":
    main()
