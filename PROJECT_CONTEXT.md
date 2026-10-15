# Spanky TTS — Project Context

> Read this document before proposing or implementing substantial changes.

## Project Overview

Spanky TTS is a custom Android Text-to-Speech engine designed primarily for the **BOOX Go Color II** and **BOOX NeoReader**.

NeoReader remains the ebook reader.

Spanky TTS is responsible for narration.

The long-term goal is to make reading an EPUB in NeoReader feel closer to a professionally narrated audiobook without replacing NeoReader's rendering, navigation, highlighting, bookmarks, or library.

---

# Current Development Phase

## CURRENT CHECKPOINT: Phase 2B.2A COMPLETE; larger-generation-unit feasibility VALIDATED

The core transport architecture is already proven on the physical BOOX.

Do **not** treat this repository as a Phase 1 prototype anymore.

Completed:

```text
Phase 1    Android TTS / NeoReader integration       COMPLETE
Phase 2A   Live EPUB text anchoring                  COMPLETE
Phase 2B.1 FastAPI + OpenAI + real BOOX playback     COMPLETE
Phase 2B.2A Context-aware narration delivery         COMPLETE
Long-form chapter TTS feasibility experiment         VALIDATED / COMPLETE
```

Validated Phase 2B.2A behavior:

```text
Use surrounding EPUB context
        ↓
improve cadence / tone / continuity
        ↓
speak ONLY the exact current NeoReader request
```

Physical testing found modest improvement in some short fragments and no
surrounding EPUB words spoken. Separate generations still cause audible tone
and cadence resets, especially when NeoReader divides "Mr." and "Poe" into
different requests. A separate chapter experiment has now validated that larger
generation units materially improve narration quality and can be generated fast
enough to investigate pre-generation and caching. The experiment is not part of
Android or production backend playback. Source/audio alignment, cached slicing,
and handling of generative omissions remain to be designed and implemented.
Exact per-request audio delivery, anchoring, callback lifecycle, and cancellation
remain required.

---

# Proven End-to-End Architecture

```text
BOOX NeoReader
      ↓
Android Text-to-Speech Framework
      ↓
SpankyTTSService
      ↓
EPUB anchor / position matcher
      ↓
HTTP POST /tts
      ↓
FastAPI backend on development PC
      ↓
OpenAI gpt-4o-mini-tts
      ↓
Raw PCM 24 kHz / 16-bit / mono
      ↓
Android SynthesisCallback
      ↓
NeoReader playback
```

This entire chain has been physically verified.

---

# Hard Project Boundaries

## NeoReader remains the reader

Do not turn Spanky TTS into a replacement EPUB reader.

NeoReader remains responsible for:

- EPUB rendering
- page layout
- fonts
- page navigation
- highlighting
- bookmarks
- library management
- visual reading position

Spanky TTS should focus on:

- locating the current text in the imported EPUB
- narration context
- speech generation
- audio delivery
- cancellation
- cache/prefetch work later

## Do not rewrite book text

The original book text is authoritative.

Narration instructions/context may affect **delivery**, but should not rewrite or paraphrase the requested book text.

## Context must never become accidental speech

For Phase 2B.2A, previous/following EPUB text is context only.

Only the exact current Android/NeoReader synthesis request should be spoken.

---

# Development Environment

Primary environment:

```text
OS: Windows 11
Editor: Visual Studio Code
Language: Kotlin
Android SDK: installed
JDK: 17
Gradle: 8.2.1
Android Gradle Plugin: 8.1.0
ADB: official Android SDK platform-tools
Git / GitHub: in use
Backend: Python / FastAPI / Uvicorn
```

Repository root:

```text
C:\path\to\SpankyTTS
```

Android package:

```text
com.snippycalderone.spankytts
```

Build command:

```powershell
.\gradlew.bat assembleDebug
```

Install command:

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

---

# Current Repository Shape

```text
SpankyTTS/
│
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/snippycalderone/spankytts/
│       │   ├── MainActivity.kt
│       │   ├── SpankyTTSService.kt
│       │   └── anchor/
│       │       ├── AnchorModels.kt
│       │       ├── AnchorStorage.kt
│       │       ├── EpubTextIndexer.kt
│       │       ├── TextAnchorMatcher.kt
│       │       └── TextNormalizer.kt
│       └── res/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── .env.example
│   ├── README.md
│   └── requirements.txt
│
├── PROJECT_CONTEXT.md
├── STATUS.md
├── README.md
└── .gitignore
```

---

# Phase 1 — Verified Android TTS Behavior

Phase 1 established the Android/NeoReader integration.

Verified:

- Spanky appears as an Android TTS engine.
- NeoReader can select and invoke it.
- `SpankyTTSService` receives actual book text.
- Android `SynthesisCallback` playback works.
- `onStop()` cancellation works.

## Critical request-chunking result

A controlled test in `MainActivity` sends:

```text
exactly one speak() call
exactly 493 characters
```

The service receives:

```text
exactly one SynthesisRequest
exactly the same 493 characters
```

Therefore:

> Android's normal TTS framework is not splitting the long utterance.

NeoReader performs the observed upstream chunking.

Do not re-investigate this unless new evidence contradicts it.

---

# Important TextToSpeechService Constraint

`TextToSpeechService.onSynthesizeText()` is effectively serialized through the synthesis thread/callback lifecycle.

Do not design a solution that holds request #1 open while waiting for future NeoReader synthesis requests to arrive.

That blocks the synthesis pipeline and prevents the hoped-for aggregation behavior.

Therefore naive "wait for the next few NeoReader chunks, combine them, then answer request #1" is not a valid architecture.

This constraint is one reason Phase 2A uses EPUB knowledge rather than trying to aggregate future Android callbacks.

---

# Phase 2A — Live EPUB Text Anchoring

## Purpose

NeoReader does not provide useful book/chapter/page/offset metadata through the Android TTS request.

Observed request metadata contains ordinary TTS fields but no reliable:

- book ID
- EPUB path
- chapter identifier
- page number
- source character offset

The incoming **text itself** is therefore the anchor.

## Anchor concept

Logical position:

```text
Active Book
+
EPUB Section
+
Normalized Character Offset
```

## EPUB import/indexing

The user imports the EPUB into Spanky TTS.

The app copies it into app-private storage and builds an index.

Primary index path:

```text
META-INF/container.xml
        ↓
rootfile full-path
        ↓
OPF
        ↓
manifest
        ↓
spine
        ↓
ordered readable sections
```

The indexer:

- does not hardcode an OPF filename
- resolves relative EPUB paths
- handles dot segments
- handles percent-encoded internal paths
- strips query/fragment components for ZIP lookup
- preserves the actual resolved ZIP entry name
- filters readable HTML/XHTML spine items
- falls back to broad HTML/XHTML scanning if package/spine indexing cannot produce sections

Test EPUB validation:

```text
The Reptile Room
package=content.opf
spine items=30
indexed spine sections=30
fallback=false
```

Never hardcode this book or its text. It is only a validation fixture.

## Normalization

Incoming NeoReader text and indexed EPUB text are normalized consistently.

Current normalization includes:

- lowercase
- smart apostrophe → straight apostrophe
- smart quotes → straight quotes
- NBSP → regular space
- CR/LF/tab → spaces
- repeated whitespace collapse
- trim

Punctuation/words are otherwise preserved enough for accurate matching.

## Matcher behavior

### Unanchored

Global establishment remains conservative.

Very short/common chunks do not independently establish a global anchor.

### Anchored

The matcher:

1. searches near the rolling cursor
2. tracks ordinary forward chunks
3. uses a narrow local window for short chunks
4. preserves state if a short chunk is locally ambiguous
5. can search farther in the current section
6. can perform global recovery when needed

### Cross-section re-anchor

A unique match in another section is not immediately committed.

It becomes a pending candidate.

The following request must uniquely continue near that candidate before the active section/cursor changes.

This avoids false cross-section jumps.

The Phase 2A BOOX logs showed why this confirmation matters: a passage repeated
in the EPUB contents section briefly drew an earlier matcher into that section.
A later Chapter 2 jump was then logged as pending and was committed only after
the next request continued there. The raw validation captures were local test
artifacts; this is the finding to retain for future matcher work.

### Known matcher limitation

Some tiny/common fragments can remain ambiguous.

The matcher intentionally avoids guessing.

A following distinctive request generally catches the cursor up.

Do not "fix" this by blindly selecting the nearest duplicate without a strong reason and physical validation.

---

# Phase 2B.1 — Backend / OpenAI Transport

## Backend

Location:

```text
backend/
```

Framework:

```text
FastAPI
```

Server:

```text
Uvicorn
```

OpenAI model:

```text
gpt-4o-mini-tts
```

Endpoints:

```text
GET /health
POST /tts
```

## Current backend request

```json
{
  "text": "<exact incoming Android synthesis request>",
  "voice": "cedar",
  "instructions": "Read naturally as a professional audiobook narrator. Use natural pacing and expressive but restrained delivery."
}
```

Phase 2B.1 intentionally uses:

```text
1 Android synthesis request
=
1 backend request
=
1 OpenAI speech generation
```

Do not silently change that behavior while working on unrelated bugs.

## Current backend response

Successful response is raw PCM:

```text
Content-Type: application/octet-stream
X-Audio-Sample-Rate: 24000
X-Audio-Encoding: pcm_s16le
X-Audio-Channels: 1
```

Audio format:

```text
24,000 Hz
signed 16-bit little-endian PCM
mono
```

No WAV header.

No base64.

## Validation/error behavior

Backend currently handles:

- missing `OPENAI_API_KEY` → HTTP 503
- blank text → HTTP 400
- text above 5000 characters → HTTP 413
- OpenAI/API failures → sanitized HTTP 502

Do not leak API keys or authentication headers to logs.

---

# API Key Security

The OpenAI API key exists only in:

```text
backend/.env
```

Tracked template:

```text
backend/.env.example
```

The Android app must never contain the key.

The BOOX must never receive the key.

The Android request to the backend contains only narration data, not OpenAI credentials.

Git ignore coverage includes:

```text
backend/.env
backend/.venv/
backend/*.pcm
backend/*.wav
backend/**/__pycache__/
backend/**/*.pyc
```

---

# Development Networking

The Android backend URL is read at build time from the ignored root
`local.properties` file:

```properties
SPANKY_TTS_BACKEND_URL=http://<development-pc-ip>:8000/tts
```

Replace the placeholder with the development PC's LAN address for BOOX builds.
If unset, the safe build default is `http://127.0.0.1:8000/tts`. The service
reads `BuildConfig.BACKEND_TTS_URL`; changing the local property requires a
rebuild. This is temporary LAN configuration.

Uvicorn LAN command:

```powershell
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

During prior physical testing, the BOOX browser accessed the configured LAN
health endpoint:

```text
http://<development-pc-ip>:8000/health
```

and received HTTP 200.

Windows configuration used during testing:

- trusted home network profile: Private
- inbound TCP port 8000 allowed on Private profile only

Android currently allows cleartext HTTP for this LAN development path.

Treat the locally configured LAN URL and broad cleartext allowance as temporary development configuration.

Do not expose the backend on untrusted/public networks.

---

# Android Phase 2B.1 Integration

Primary file:

```text
SpankyTTSService.kt
```

Networking:

```text
OkHttp 4.11.0
```

Current service flow:

```text
receive SynthesisRequest
        ↓
existing Phase 2A matcher processing
        ↓
build backend JSON
        ↓
POST /tts
        ↓
validate response
        ↓
callback.start(24000, PCM_16BIT, mono)
        ↓
audioAvailable(...) in maxBufferSize chunks
        ↓
callback.done()
```

## Callback rules

Preserve these rules:

- call `start()` only after a valid backend response
- never pass an audio buffer larger than `callback.maxBufferSize`
- check cancellation between chunks
- do not call `done()` after cancellation
- do not call `callback.stop()`
- use `callback.error()` for real synthesis failures
- do not fall back to the old 440 Hz tone

## Cancellation

`onStop()`:

- sets the existing cancellation state
- cancels the active OkHttp call when present

Cancellation has been physically verified:

1. during PCM delivery
2. during an in-flight NeoReader backend request

Cancellation-related network exceptions should be treated as cancellation, not unexpected backend failure.

---

# Physical Phase 2B.1 Verification

## Controlled long test

The existing controlled test sends 493 characters.

Verified:

- OpenAI generated actual speech
- BOOX played it through the Android TTS path
- the request completed normally

Second run:

- user pressed Stop
- `onStop()` fired
- PCM delivery stopped
- cancellation path was logged

## NeoReader test

Validation book:

```text
The Reptile Room
```

Test flow:

1. import EPUB into Spanky
2. open Chapter 5 in NeoReader
3. start NeoReader TTS
4. allow narration to progress
5. stop during the page

Verified:

- chapter title generated real speech
- first distinctive sentence established the Chapter 5 anchor
- later chunks tracked sequentially
- real OpenAI audio played for NeoReader chunks
- stop during a later request cancelled the active backend call

This proves the core product concept.

---

# Observed Phase 2B.1 Performance

The controlled 493-character requests take several seconds to fully generate.

In the live NeoReader test, small requests commonly completed around:

```text
~0.7–1.8 seconds
```

with occasional requests around:

```text
~2.8 seconds
```

Many sequential NeoReader requests reused the same client connection to the backend.

Therefore current pauses are not primarily a "new TCP connection every chunk" problem.

The important remaining causes are:

- OpenAI generation latency
- NeoReader's small chunk boundaries
- each chunk being performed independently

---

# Why Phase 2B.2A Exists

Example NeoReader fragment:

```text
"And of course,"
```

When synthesized alone, the model does not know what follows.

It may perform the comma like an ending instead of a continuation.

The current issue is not whether speech works.

It does.

The issue is whether independent chunks sound like one continuous audiobook performance.

---

# Phase 2B.2A — Completed Implementation and Observed Limit

## Goal

Give OpenAI surrounding context while speaking only the exact requested chunk.

Concept:

```text
Previous EPUB text
        +
Current request
        +
Following EPUB text
        ↓
context-aware narration guidance
        ↓
OpenAI TTS
        ↓
audio for CURRENT REQUEST ONLY
```

## Original design requirements

Before implementation, determine:

1. how much previous/following context to use
2. where the context should be extracted
3. what Android sends to the backend
4. how backend schema separates context from text-to-speak
5. how instructions make "speak only current text" explicit
6. how to prevent accidental context narration
7. how to test continuity objectively
8. what latency/cost overhead is introduced

## Initial test target

Use known short fragments that sounded unnatural in Phase 2B.1, especially continuation phrases ending in commas.

Compare:

```text
isolated generation
vs.
context-aware generation
```

Do not attempt prefetch/cache/alignment in the same first change unless explicitly requested.

---

# Larger-Generation-Unit Feasibility — Validated

The standalone `experiments/chapter_tts/` utility extracts EPUB chapters and
generates coherent blocks. Chapter Five of *The Reptile Room* was tested as five
large blocks. Listening found better continuity, pacing, dialogue transitions,
and overall audiobook quality than independent tiny requests. The planner's
120-character non-final tail protection and exact-join assertion preserve the
extracted source text. Text and ending fidelity instructions improved isolated
final-paragraph delivery; a later full-chapter run still omitted the absolute
final sentence. This is an unresolved generative audio fidelity issue, not an
EPUB extraction or block-planning text loss.

The experiment does not provide aligned audio slices or change NeoReader
playback. Only exact current-request audio may be returned to NeoReader.

---

# Phase 2B.2B — Next Milestone: Alignment and Cached Slicing

The larger-generation-unit feasibility question has been answered positively.
The next design and implementation work must map source spans to verified audio
spans before longer clips can serve NeoReader's smaller requests.

Required design topics:

- audio/text alignment and beginning/end omission detection
- deterministic source-to-audio mapping and cache keys
- slicing cached audio to the exact current NeoReader request
- pre-generation and look-ahead strategy
- cache-miss fallback to the existing live per-request TTS path
- eventual chapter-boundary and final-block handling

Critical constraint:

> A paragraph-sized audio clip cannot simply be returned for the first tiny NeoReader request.

Doing so would cause duplication/highlighting/request-boundary problems when NeoReader sends the following requests.

Larger pre-generated clips require accurate audio/text alignment and slicing
before integration. Unverified or missing slices fall back to live per-request
TTS.

Do not implement naive request aggregation that violates the Android callback/request contract.

---

# Longer-Term Roadmap

After 2B.2:

## Usability

- in-app backend URL setting (the current URL is configured locally at build time)
- voice selection
- narration presets
- better network/error UI
- voice preview
- persistent settings

## Cache

- avoid repeated API charges
- improve replay/startup speed
- cache key should include at least text/model/voice/instructions/relevant settings

## Narration Director

Potential analysis:

```text
Mood
Pace
Energy
Emotion
Dialogue intensity
Pause behavior
```

The director should affect delivery, not rewrite the book.

## Character Awareness

Experimental future goal:

- distinguish narration from dialogue
- detect recurring speakers
- preserve consistent character delivery
- avoid random voice switching

Do not implement this until base continuity/latency behavior is reliable.

---

# BOOX Settings Used During Validation

```text
Auto-start: ON
Freeze: OFF
Pause app activity if unused: OFF
Stay active in background: Unlimited
```

These settings improved service availability during repeated NeoReader tests.

---

# Logging Expectations

Keep logs concise but useful.

Important Android events include:

- synthesis request number
- text length
- locale/rate/pitch
- anchor status
- backend request start
- backend status
- generation/network elapsed time
- PCM byte count
- callback start
- delivered chunk count
- completion
- cancellation
- errors

Avoid logging secrets.

Do not add excessive per-audio-buffer logging long-term unless actively diagnosing callback delivery; it can make logs unnecessarily noisy.

---

# Coding Agent Rules

When working on this repository:

1. Read `PROJECT_CONTEXT.md` and `STATUS.md` first.
2. Determine the exact active phase before changing code.
3. Preserve working Phase 2A anchoring unless the task explicitly concerns anchoring.
4. Preserve the Phase 2B.1 backend/PCM/cancellation path unless the task explicitly changes it.
5. Do not redesign multiple layers at once.
6. Prefer small, testable changes.
7. Build after meaningful Android changes.
8. Run backend syntax/tests after meaningful backend changes.
9. Never hardcode or print API credentials.
10. Never commit `backend/.env`.
11. Never let context text accidentally become spoken text.
12. Do not claim success until physical BOOX behavior is verified when the task depends on NeoReader.
13. Prefer ADB/logcat evidence over assumptions.
14. Do not implement future cache/alignment/director features unless requested.
15. Keep code understandable for a developer who is actively learning the project.

---

# Required Validation Workflow

For meaningful Android changes:

```powershell
.\gradlew.bat assembleDebug
git status --short
```

Do not install/commit/push unless the current task explicitly calls for it.

For physical testing:

```powershell
adb devices
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb logcat -c
adb logcat SpankyTTS:I AndroidRuntime:E *:S
```

For the backend:

```powershell
backend\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Health:

```powershell
Invoke-RestMethod 'http://<development-pc-ip>:8000/health'
```

---

# Agent Response Style

The project owner is learning development and wants exact, practical guidance.

Prefer:

- plain English
- exact filenames
- exact PowerShell commands
- small implementation steps
- a recommended approach when multiple options exist
- clear distinction between proven behavior and proposed design

When a task is complete, report:

```text
What changed:
-

Why:
-

Files modified:
-

Build/test status:
-

What to test next:
-
```

Do not bury the next action.

---

# Current Checkpoint

Phase 2B.1 has been committed and pushed.

The current known-good system can:

```text
Open EPUB in NeoReader
        ↓
Start Text-to-Speech
        ↓
Spanky receives NeoReader chunk
        ↓
Spanky anchors it against imported EPUB
        ↓
Spanky calls local backend
        ↓
backend calls gpt-4o-mini-tts
        ↓
raw PCM returns
        ↓
BOOX speaks real AI narration
        ↓
Stop cancels active work
```

The product concept is proven.

The next job is to make independent NeoReader chunks sound like one continuous narration performance.

---

# End Goal

```text
Open book in NeoReader
        ↓
Press Text-to-Speech
        ↓
Spanky identifies exact book position
        ↓
Spanky understands nearby narrative context
        ↓
natural expressive speech begins
        ↓
future prefetch/cache hides avoidable latency
        ↓
continue reading normally in NeoReader
```

**NeoReader handles reading. Spanky TTS handles narration.**
