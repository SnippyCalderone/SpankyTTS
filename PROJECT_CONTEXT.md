# Spanky TTS — Project Context

> Read this document before proposing or implementing substantial changes.

## Project Overview

Spanky TTS is a custom Android Text-to-Speech engine designed primarily for the **BOOX Go Color II** and **BOOX NeoReader**.

NeoReader remains the ebook reader.

Spanky TTS is responsible for narration.

The long-term goal is to make reading an EPUB in NeoReader feel closer to a professionally narrated audiobook without replacing NeoReader's rendering, navigation, highlighting, bookmarks, or library.

---

# Current Development Phase

## CURRENT CHECKPOINT: M0D.1 NEXT; Master Voice Library M0A–M0C COMPLETE LOCALLY

The core transport architecture is already proven on the physical BOOX.

Do **not** treat this repository as a Phase 1 prototype anymore.

Completed:

```text
Phase 1    Android TTS / NeoReader integration       COMPLETE
Phase 2A   Live EPUB text anchoring                  COMPLETE
Phase 2B.1 FastAPI + OpenAI + real BOOX playback     COMPLETE
Phase 2B.2A Context-aware narration delivery         COMPLETE
Long-form chapter TTS feasibility experiment         VALIDATED / COMPLETE
Master Voice Library M0A–M0C                         COMPLETE LOCAL CATALOG
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
Android or production backend playback. The standalone alignment candidate
requires human verification; cached slicing and handling of generative
omissions remain open work.
Exact per-request audio delivery, anchoring, callback lifecycle, and cancellation
remain required.

The standalone one-block alignment experiment has produced a Whisper ASR/source
candidate map and review clips, but its saved result is `ALIGNED_BUT_UNCERTAIN`.
Its human listening review and subsequent cached playback work are deferred,
with the research and limitations preserved. Neither verified cached slicing
nor Android cached playback has been implemented.

M0D.1 is the immediate development priority: spoiler-aware character research
or manual entry, cited editable profiles, provider-neutral vocal traits, and
three Gemini-specific voice-design prompt drafts. M0D.2 creates approved
persistent voices; M0D.3 auditions and refines them; M0D.4 experiments with
Gemini narration using short manually attributed dialogue and controlled
chapter excerpts independently of Android. Automated attribution, scene-level
voice switching, and full-book character mapping are deferred. These stages
are planned, not implemented. The library contains 16 synchronized Gemini
voices and one preferred Gabriel de León assignment, but it is not used by
narration generation or Android. See `ROADMAP.md` for sequence and dependencies.

Gemini 3.8 Flash TTS is the selected target for character voices and planned
audiobook generation. OpenAI models are planned for research, dossier and voice
prompt work, and optional future narration analysis/orchestration. The current
physically verified BOOX path still uses OpenAI `gpt-4o-mini-tts`; the standalone
chapter and alignment experiments also used OpenAI audio. Gemini has not
replaced that backend and has not been validated in NeoReader.

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
- planned aligned cache and look-ahead work

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
├── experiments/
│   ├── alignment/
│   ├── chapter_tts/
│   └── gemini_tts/
├── master_voice_library/
│   ├── migrations/
│   ├── tests/
│   └── README.md
│
├── PROJECT_CONTEXT.md
├── STATUS.md
├── ROADMAP.md
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

This scoped first change is complete. New alignment and cache work follows the
separate Phase 2B.2B milestones in `ROADMAP.md`.

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

# Phase 2B.2B — Deferred Engineering Milestone: Alignment and Cached Playback

The larger-generation-unit feasibility question has been answered positively.
The saved experiment aims to map known EPUB source offsets to audio timestamps
in one existing approximately 3,000-character generated block. Compare forced
alignment, transcription with word timestamps, available model/provider timing
metadata, and hybrid approaches before selecting an alignment method. Detect
missing speech at the beginning and end; a text plan alone does not prove the
model actually spoke every word.

## Preserved engineering strategy

**Later core engineering** is the required playback path. Generate natural, larger
narration blocks ahead of demand; align their audio to exact EPUB source spans;
then serve verified slices for whatever small requests NeoReader actually makes.
The project is not trying to predict NeoReader's request boundaries before
generation. The Phase 2A matcher supplies the request's source position when it
is reliable. A deterministic source-span to audio-span map supplies the slice.

```text
EPUB source → coherent generation → text/audio alignment → verified span map
                                                       ↓
NeoReader request → Phase 2A anchor → exact source span → cached PCM slice
                                                       ↓
                                           SynthesisCallback → NeoReader
```

**Narrator Lab** is an independent experimental path; the current
Gemini lab lives under `experiments/gemini_tts/`. It can compare voices,
narration instructions,
pacing, emotional range, scene dynamics, dialogue delivery, interruptions, and
em-dash handling using A/B runs of the same short source excerpt. It must
preserve exact book text and must not redefine the deferred alignment path. Experimental
results do not become Android playback behavior until the relevant architecture
has been proven.

Dialogue-direction principle: speech verbs, dialogue tags, adverbs, and nearby
narration are performance cues for their associated quoted dialogue, even when
the cue follows the quote. Examples include “said fiercely,” “hissed,”
“impatiently,” “whispered,” and “excitedly.” The attribution itself should still
be read naturally as narration.

## Exact request delivery and fallback

NeoReader expects the callback audio for the current synthesis request to match
that request. Returning a whole paragraph or block for a smaller request would
speak future book words early, then duplicate them when NeoReader requests those
words, and desynchronize its request progression and highlighting. Surrounding
EPUB text may inform generation, but it must not leak into the delivered slice.

The planned `SpankyTTSService` decision path is:

```text
NeoReader request
  → reliable Phase 2A source anchor?
  → verified aligned cached slice for the exact request?
      yes: deliver that PCM through the existing callback lifecycle
      no:  use the existing live per-request OpenAI TTS path
```

An ambiguous anchor, incomplete alignment, missing cache entry, or unverified
boundary cannot authorize cached audio. Keep the proven live path, callback
size limits, cancellation, and backend-only API credentials. Alignment and
slicing are not yet working; this is a proposed decision path.

Generation strategy and delivery remain separate long term. Narrator and
character voices or scene audio may eventually produce one coherent master
generation, but the same source/audio alignment abstraction, cache, and exact
NeoReader request slicing should deliver it. NeoReader need not know how the
master audio was produced. Production character voices and scene effects depend
on a proven cached aligned playback path; isolated quality experiments may run
earlier.

Required design topics:

- single-block alignment and beginning/end omission detection
- deterministic source-to-audio mapping and cache keys tied to text, model,
  voice, instructions, and relevant settings
- verified slice boundaries without clipped or leaked meaningful words
- replay of observed NeoReader request patterns before Android integration
- pre-generation of several natural blocks into a small look-ahead queue
- cache-miss fallback and eventual chapter-boundary/final-block handling

Critical constraint:

> A paragraph-sized audio clip cannot simply be returned for the first tiny NeoReader request.

Doing so would cause duplication, highlighting, and request-boundary problems when NeoReader sends the following requests.

Larger pre-generated clips require accurate audio/text alignment and slicing
before integration. Unverified or missing slices fall back to live per-request
TTS.

Do not implement naive request aggregation that violates the Android callback/request contract.

---

# M0D Voice Design and Longer-Term Capabilities

The M0D.1–M0D.4 sequence is defined in `ROADMAP.md`. M0D.1 reuses existing
character and voice records, accepts manual profiles, and optionally uses
OpenAI online research or user-provided EPUB content within a spoiler cutoff.
It compiles provider-neutral voice traits into three Gemini voice-design prompt
drafts without automatically creating voices. Paid research requires explicit
user authorization; saved results and citations should be reused. Viewing or
editing saved dossiers, compiling prompts, and offline tests make no API calls.
M0D.2 records new Gemini provider IDs and lineage only after explicitly
approved creation or regeneration; M0D.3 uses standardized dialogue for
audition and explicit preferred assignment. M0D.4 can begin with short manually
attributed dialogue and controlled chapter excerpts. The existing 16 voices and preferred
Gabriel de León assignment must be preserved. Ashdrinker refinement is planned
with an end-of-first-book spoiler cutoff.

Automated character aging, permanent or temporary vocal-change detection,
flashback and nonlinear timeline analysis, scene-level voice assignment, and
exact EPUB text-range to voice-state mapping are deferred. Store future voice
variants without implementing this evolution engine in M0D.1–M0D.3.

`ROADMAP.md` is the source for sequence and dependencies. The following
production playback capabilities follow a proven aligned cached path:

## Usability

- in-app backend URL setting (the current URL is configured locally at build time)
- voice selection
- narration presets
- better network/error UI
- voice preview
- persistent settings

## Cache management

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

Later production goal, with local library management and isolated experiments
already allowed:

- distinguish narration from dialogue
- detect recurring speakers
- preserve consistent character delivery
- avoid random voice switching

Do not integrate this into production playback until aligned cached delivery is
proven. Character voices and scene effects share its source/audio mapping and
exact-request delivery contract.

The standalone `master_voice_library/` package has completed M0A–M0C: versioned
SQLite catalog, read-only Gemini synchronization, scoped characters, local
annotations/tags, assignment history, and preference management. Its first
complete sync imported 16 voices. The Empire of the Vampire series scope contains
Gabriel de León, whose preferred slot 1 voice is Gemini “Gabriel de León 2”.
This local assignment does not alter the Android or backend synthesis path.

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
14. Scope new work to the requested `ROADMAP.md` milestone; do not pull later features into an earlier proof.
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

Completed repository work includes Phase 2B.2A context-aware delivery, the
validated standalone larger-generation-unit experiment, Master Voice Library
M0A–M0C, and the earlier Phase 1, Phase 2A, and Phase 2B.1 milestones.
M0D.1 is the next development step. Phase 2B.2B is deferred. Its standalone
alignment candidate remains `ALIGNED_BUT_UNCERTAIN`; verified slicing and
cached NeoReader playback are not implemented.

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

The next job is the M0D.1 research and voice-profile foundation. Later, resume
the saved block's listening review and resolve uncertainty before verifying
source/audio lookup. Verified slicing, request simulation, and cached Android
delivery follow that proof.

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
