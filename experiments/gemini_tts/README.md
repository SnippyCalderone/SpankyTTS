# Gemini Narrator Lab

This isolated CLI compares one narrator voice across two deliveries of the same
Chapter Five EPUB-source passage. It does not change Android, the backend,
alignment, or the OpenAI chapter experiment. Generation requires `--generate`;
`--dry-run` makes no Gemini API call and writes no output.

## Setup (PowerShell, from the repository root)

The dedicated virtual environment already exists. Install only its pinned SDK:

```powershell
.\experiments\gemini_tts\.venv\Scripts\python.exe -m pip install -r .\experiments\gemini_tts\requirements.txt
```

Only the Google Gen AI SDK is a direct dependency. WAV inspection, hashing,
metadata, and tests use the Python standard library. The SDK reads the process
environment; this CLI explicitly selects `GEMINI_API_KEY` so another Google key
cannot silently take precedence. Keep keys in your local environment, never in
tracked files or command arguments. `.env` and `*.local.json` in this directory,
the virtual environment, and `output/` are ignored by Git.

## The fixed source and profiles

`passage.json` points to the ignored local Chapter Five source produced by the
OpenAI chapter experiment. The CLI validates the full source hash, then extracts
the 609-character `[3623, 4232)` slice and checks its SHA-256. The book text is
not copied into this directory's tracked files. If the local fixture is absent
or changed, both modes stop before an API call.

`profiles.json` defines `neutral` and `character_aware`. Both use one exact text
block and one narrator voice. Only the `speech_metadata.style` annotation
changes. Delivery cues are metadata, never inserted into the spoken text.
The character-aware profile asks for subtle changes based on dialogue and
attribution without switching voice. Such cues cannot guarantee distinct,
persistent character identities or perfect spoken-word fidelity; review the
saved audio against the source before using it for any later alignment work.

For a later character registry, use an ignored `voices.local.json` with entries
such as `{"characters":{"character_name":{"provider":"google_gemini", "voice_id":"..."}}}`.
Keep provider and ID together so a voice from another service is never passed
to Gemini by accident. This first lab does not load or switch character voices.

## Dry runs and tests (no credits)

```powershell
.\experiments\gemini_tts\.venv\Scripts\python.exe -m unittest discover -s .\experiments\gemini_tts\tests -v
.\experiments\gemini_tts\.venv\Scripts\python.exe .\experiments\gemini_tts\narrator.py --dry-run --profile neutral
.\experiments\gemini_tts\.venv\Scripts\python.exe .\experiments\gemini_tts\narrator.py --dry-run --profile character_aware
```

Dry-run output gives the offsets, source and request hashes, profile version,
model, voice, and a text-equality flag. It does not print the book passage.

## Paid generation (requires separate approval)

Each command below starts **one** audio-generation operation; the SDK may retry
transient HTTP failures internally. Do not run either until that approval is given:

```powershell
.\experiments\gemini_tts\.venv\Scripts\python.exe .\experiments\gemini_tts\narrator.py --generate --profile neutral
.\experiments\gemini_tts\.venv\Scripts\python.exe .\experiments\gemini_tts\narrator.py --generate --profile character_aware
```

The defaults are model `gemini-3.8-flash-tts` and prebuilt voice `Gacrux`.
Use `--model MODEL_ID`, `--voice VOICE_NAME_OR_ID`, or `--output-dir PATH` to
override them. Use the **same** model and voice on both calls for a controlled
profile comparison. A voice ID from another provider must first be confirmed
compatible with the Gemini API. Do not place local voice IDs in tracked files.

Successful calls write `narration.wav` and `run.json` under a timestamped,
ignored `output/` directory. WAV must be 24 kHz, mono, 16-bit PCM. Metadata
records the exact source and request hashes, model, voice, profile version,
style hash, latency, WAV properties, and available usage fields. Failed calls
write sanitized error metadata when an output directory was created. The error
record includes a failure stage, exception class, HTTP status when available,
recognized provider code and reason, and a fixed diagnostic message. Raw SDK
messages, request contents, response bodies, URLs, authorization headers, and
API keys are never saved. A plain HTTP 429 remains ambiguous between quota and
rate limits unless the provider supplies a recognized reason.

The existing OpenAI `part_002.mp3` contains this excerpt within a longer block.
A word-level A/B requires locating its audio span or separately generating the
same short text with OpenAI. This lab does not perform alignment or synthesis
for that comparison.
