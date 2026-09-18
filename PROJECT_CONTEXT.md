# Spanky TTS

## Project Overview

Spanky TTS is a custom Android Text-to-Speech engine intended primarily for a **BOOX Go Color II** e-ink tablet.

The primary reading application will remain **BOOX NeoReader**.

The goal is **not** to build a replacement ebook reader.

Instead, Spanky TTS should register itself with Android as a normal system TTS engine so that NeoReader can send text to it using Android's standard Text-to-Speech framework.

Spanky TTS will then send that text to a cloud AI TTS provider, initially the **OpenAI Speech API**, receive high-quality synthesized speech, and stream that audio back through Android's `TextToSpeechService` / `SynthesisCallback`.

The long-term goal is to produce audiobook-quality narration while continuing to use NeoReader for EPUB rendering, navigation, highlighting, bookmarks, library management, and reading.

---

# Primary Goal

Create an Android application that appears as a selectable system TTS engine:

```text
NeoReader
    │
    ▼
Android Text-to-Speech Framework
    │
    ▼
Spanky TTS
    │
    ▼
OpenAI Speech API
    │
    ▼
AI-generated PCM audio
    │
    ▼
Android SynthesisCallback
    │
    ▼
NeoReader playback
```

The first milestone is simply proving that this architecture works reliably on the BOOX Go Color II.

Do not prematurely build advanced AI narration features until this fundamental integration is confirmed.

---

# Development Environment

Primary development environment:

* Windows PC
* Visual Studio Code
* Kotlin
* Android SDK
* Gradle / Gradle Wrapper
* ADB
* Git
* VS Code AI coding agent

Android Studio may be installed for:

* Android SDK management
* Platform/build-tool installation
* emulator support if needed
* advanced Android debugging if necessary

However, **VS Code should remain the primary editor and development interface**.

The project must be buildable entirely from the command line with:

```powershell
.\gradlew.bat assembleDebug
```

The resulting APK should be installable using:

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

---

# Language and Architecture

Use:

* **Kotlin**
* Android SDK
* Gradle Kotlin DSL (`build.gradle.kts`)
* Android `TextToSpeechService`
* OkHttp or another lightweight HTTP client
* Kotlin serialization or equivalent lightweight JSON handling
* Android DataStore for preferences
* secure local storage for secrets where appropriate

Avoid unnecessary frameworks.

This project is primarily a **background TTS service with a small configuration UI**, not a traditional feature-heavy Android application.

Prefer simple, maintainable architecture over excessive abstraction.

---

# Phase 1 — Proof of Concept

## Objective

Prove that NeoReader can successfully communicate with our custom Android TTS service.

Phase 1 is complete only when this entire flow works:

```text
NeoReader
    ↓
Spanky TTS receives text
    ↓
Spanky TTS logs the request
    ↓
Spanky TTS sends text to OpenAI
    ↓
OpenAI returns speech
    ↓
Spanky TTS returns audio through Android TTS
    ↓
Audio is heard while using NeoReader
```

## Phase 1 Requirements

Implement:

1. Android `TextToSpeechService`
2. Proper Android manifest registration as a TTS engine
3. English / `en-US` language support
4. `onSynthesizeText()`
5. `onStop()`
6. logging of incoming TTS requests
7. OpenAI API communication
8. PCM audio response handling
9. audio delivery through `SynthesisCallback`
10. simple application settings UI
11. API key entry
12. voice selection
13. narration-instructions field
14. Test Voice button

---

# Extremely Important Phase 1 Logging

Before trying to make the narration sophisticated, we need to discover exactly how **NeoReader sends TTS requests**.

Every synthesis request should log useful diagnostic information.

Example:

```text
SpankyTTS: SYNTHESIS REQUEST RECEIVED

Characters: 247
Locale: en-US
Speech Rate: 1.0
Pitch: 1.0

Text:
"Kvothe looked toward the window. Outside, the wind had begun to rise..."
```

Log:

* complete incoming text
* character count
* locale
* speech rate
* pitch
* request timing
* request sequence/order if possible
* cancellation events
* errors
* OpenAI latency
* audio generation duration if measurable

Do not expose the user's OpenAI API key in logs.

The purpose of this logging is to determine whether NeoReader sends:

* sentences
* paragraphs
* pages
* multiple paragraphs
* some other chunk size

This information will determine the architecture of later phases.

---

# OpenAI TTS Integration

Initial provider:

**OpenAI Speech API**

Initial model:

```text
gpt-4o-mini-tts
```

The application should initially expose:

```text
Provider:
OpenAI

Model:
gpt-4o-mini-tts

Voice:
User selectable

Narration Instructions:
User editable

Playback Speed:
User configurable
```

The exact supported voice list should be isolated in configuration so that it can be updated later without restructuring the application.

---

# Narration Instructions

The OpenAI TTS request should keep the **book text** separate from **narration instructions**.

Never rewrite the actual book content unless explicitly required for technical reasons.

Example narration instructions:

```text
Narrate as a professional fantasy audiobook narrator.

Use natural conversational cadence and varied pacing.

Allow dialogue to carry more emotion than exposition.

Use subtle emotional changes appropriate to the meaning of the text.

Slow slightly during atmospheric or descriptive passages.

Respect punctuation and paragraph boundaries with natural pauses.

Avoid exaggerated theatrical delivery.

Maintain a consistent mature narrator voice.
```

The user should eventually be able to edit this text.

---

# API Key Security

Never hardcode the OpenAI API key in:

* Kotlin source code
* Git-tracked files
* Gradle files
* GitHub
* logs

Bad:

```kotlin
val apiKey = "sk-proj-..."
```

The user should enter the API key through the application UI.

Store it locally using an appropriate Android secure-storage approach.

The project should also ensure that secret-containing local files are excluded through `.gitignore` where relevant.

---

# Audio Strategy

Prefer requesting a format appropriate for direct Android TTS playback.

The ideal architecture is:

```text
OpenAI streaming PCM
        │
        ▼
audio chunks arrive
        │
        ▼
SynthesisCallback.audioAvailable(...)
        │
        ▼
NeoReader playback
```

We want to minimize startup latency.

Avoid architectures requiring the entire MP3 to download and decode before playback unless streaming PCM proves technically unreliable.

Correct Android sample rate / audio format / channel configuration must be established before sending audio to the callback.

Do not fake or guess audio format metadata.

---

# Phase 1 UI

Keep the UI extremely simple.

Example:

```text
┌─────────────────────────────────┐
│          SPANKY TTS             │
│                                 │
│ OpenAI API Key                  │
│ [••••••••••••••••••••••••]     │
│                                 │
│ Voice                           │
│ [ Cedar                    ▼ ]  │
│                                 │
│ Playback Speed                  │
│ [──────●────────] 0.95x         │
│                                 │
│ Narration Instructions          │
│ ┌─────────────────────────────┐ │
│ │ Narrate as a professional  │ │
│ │ audiobook narrator...      │ │
│ └─────────────────────────────┘ │
│                                 │
│          [ Test Voice ]         │
│                                 │
│ TTS Engine Status               │
│ Ready                           │
└─────────────────────────────────┘
```

Do not spend significant development time making the interface visually elaborate during Phase 1.

Functionality is more important.

---

# Phase 1 Acceptance Criteria

Phase 1 is considered successful when all of these are true:

* Spanky TTS installs on the BOOX Go Color II
* Android recognizes Spanky TTS as an available TTS engine
* Spanky TTS can be selected as the preferred Android TTS engine
* the app can successfully generate a Test Voice response
* NeoReader recognizes and uses Spanky TTS
* NeoReader sends readable text to `onSynthesizeText()`
* incoming NeoReader text is visible in debug logs
* OpenAI successfully receives the text
* OpenAI successfully generates speech
* generated audio is returned to Android
* speech is audible while NeoReader remains the active reader
* stopping TTS correctly cancels synthesis/playback
* no API credentials appear in source control or logs

Do **not** proceed to advanced architecture until these items have been tested on the physical BOOX device.

---

# Phase 2 — Usability

Only begin Phase 2 after Phase 1 works.

Potential Phase 2 features:

* improved settings screen
* narration presets
* voice previews
* speed control
* error messages
* connectivity handling
* API usage/error reporting
* automatic retries
* better cancellation behavior
* configurable audio buffering
* persistent settings

Narration presets may include:

```text
Fantasy Audiobook
Thriller
Science Fiction
Nonfiction
Technical
Conversational
Dramatic
Custom
```

Presets should simply control narration instructions and related settings.

They should not create unnecessary duplicated code paths.

---

# Phase 3 — Local Audio Cache

Once basic playback is reliable, implement caching.

Objective:

Do not pay to synthesize identical text repeatedly.

Cache identity should account for approximately:

```text
text
+
provider
+
model
+
voice
+
narration instructions
+
relevant audio settings
```

Example:

```text
Incoming TTS request
        │
        ▼
Generate deterministic cache key
        │
        ▼
Is audio cached?
      /     \
    YES      NO
     │        │
     ▼        ▼
   Play     OpenAI
              │
              ▼
          Save audio
              │
              ▼
             Play
```

Caching should eventually support:

* maximum cache size
* clear-cache command
* cache statistics
* deterministic filenames or database indexes
* invalidation when voice/settings change

Do not implement this until basic TTS integration has been proven.

---

# Phase 4 — Context Buffer

AI narration benefits heavily from surrounding context.

NeoReader may send very small blocks such as individual sentences.

Example requests:

```text
Request 1:
"I thought you'd left."

Request 2:
She wouldn't look at him.

Request 3:
"I almost did."
```

Eventually maintain a rolling text history:

```text
Previous:
"I thought you'd left."

Previous:
She wouldn't look at him.

Current:
"I almost did."
```

This context should help determine:

* scene mood
* cadence
* conversational intensity
* emotional delivery
* pacing

However:

**Previous text must not accidentally be spoken again.**

Context is for narration analysis only.

Only the current NeoReader text should be synthesized.

---

# Phase 5 — AI Narration Director

Eventually introduce a separate reasoning step before TTS.

Architecture:

```text
NeoReader text
      │
      ▼
Context Buffer
      │
      ▼
AI Narration Director
      │
      ▼
Narration metadata
      │
      ▼
OpenAI TTS
      │
      ▼
Audio
```

The Narration Director should analyze context without rewriting the book.

Possible output:

```text
Mood: tense
Energy: low
Pace: slightly slow
Emotion: restrained suspicion
Dialogue intensity: subtle
Pause behavior: deliberate
```

These instructions would then be passed to the speech model.

This phase should only be explored after latency and cost implications are understood.

---

# Phase 6 — Character Awareness

Long-term experimental feature.

Potentially detect dialogue and recurring characters so narration can remain more consistent.

Possible future architecture:

```text
Narrator
    → consistent neutral narration profile

Character A
    → energetic / confident delivery

Character B
    → softer / reserved delivery

Character C
    → older / deliberate delivery
```

Important:

Do not assign random voices every sentence.

Character identity must be stable.

Character detection must be sufficiently reliable before automatically affecting narration.

Do not implement this during early development.

---

# Future Provider Support

Design provider-specific code so another TTS provider could eventually be added without rewriting the Android TTS engine.

Long-term architecture may resemble:

```text
TtsProvider

├── OpenAiTtsProvider
├── FutureProvider
└── LocalTtsProvider
```

However, do not create excessive abstraction solely for hypothetical future providers.

Initially, OpenAI is the only required implementation.

---

# Future Offline Support

Possible future capability:

```text
Cloud Mode
OpenAI TTS

Offline Mode
Local Android / neural model
```

Offline AI speech is not required for the MVP.

Do not allow offline support to complicate Phase 1.

---

# Important Non-Goals

This project is NOT currently intended to become:

* an EPUB parser
* an EPUB reader
* a replacement for NeoReader
* a general audiobook library application
* a cloud backend
* a web application
* a multi-user application
* a subscription service

NeoReader remains responsible for:

* EPUB rendering
* page layout
* fonts
* page navigation
* bookmarks
* highlighting
* ebook library management

Spanky TTS should focus on **speech generation**.

---

# Development Principles

## 1. Build the smallest thing that proves the architecture

Do not overengineer.

## 2. Keep Phase 1 isolated

Do not start advanced features before NeoReader compatibility is proven.

## 3. Prefer readable code

The project owner is learning and wants to understand the code.

Avoid unnecessarily clever Kotlin.

## 4. Explain major changes

Before making a significant architectural change, explain:

* what is changing
* why
* alternatives considered
* consequences

## 5. Make incremental changes

Prefer small, testable commits.

## 6. Keep the project buildable

After meaningful changes, run:

```powershell
.\gradlew.bat assembleDebug
```

Fix compilation problems before proceeding.

## 7. Do not silently alter project goals

If an implementation decision substantially changes the architecture described here, explain it first.

## 8. Favor physical-device testing

The BOOX Go Color II is the target device.

Emulator success does not guarantee NeoReader compatibility.

## 9. Use logging heavily during integration

Especially around:

* Android TTS lifecycle
* NeoReader requests
* network calls
* audio streaming
* cancellations
* errors

## 10. Protect credentials

Never expose or commit API keys.

---

# Coding Agent Behavior

When assisting with this repository:

1. Read this document before proposing substantial changes.
2. Determine the current development phase.
3. Do not implement future-phase functionality unless requested.
4. Inspect the existing project before creating duplicate infrastructure.
5. Prefer modifying existing code over creating unnecessary parallel systems.
6. Explain proposed architecture before major refactors.
7. Use Kotlin idioms but keep code approachable.
8. Include appropriate comments for unusual Android/TTS behavior.
9. Never place API credentials in source code.
10. Build the project after significant implementation changes.
11. Report compilation errors accurately rather than hiding them.
12. When debugging BOOX behavior, prefer evidence from ADB/logcat over assumptions.
13. Do not claim NeoReader compatibility until tested on the physical device.
14. Maintain a simple changelog or progress section if useful.
15. Focus on the next actionable milestone rather than implementing the entire roadmap at once.

---

# Current Development Phase

## CURRENT PHASE: Phase 1 — Proof of Concept

The immediate objective is:

```text
BUILD
  ↓
INSTALL APK
  ↓
ANDROID RECOGNIZES SPANKY TTS
  ↓
SELECT AS TTS ENGINE
  ↓
NEOREADER SENDS TEXT
  ↓
LOG TEXT
  ↓
OPENAI GENERATES AUDIO
  ↓
RETURN AUDIO
  ↓
HEAR SPEECH
```

Nothing is more important right now than proving this chain works.

---

# First Tasks

Unless the existing repository already contains equivalent work, begin with:

1. Inspect the current repository structure.
2. Confirm Android SDK / Gradle / Kotlin configuration.
3. Create the minimum Android application structure.
4. Implement the Android `TextToSpeechService`.
5. Register the TTS service correctly in `AndroidManifest.xml`.
6. Add detailed logging for synthesis requests.
7. Add a minimal settings screen.
8. Add secure API-key entry.
9. Implement a standalone Test Voice request.
10. Implement OpenAI speech generation.
11. return generated PCM through the Android synthesis callback.
12. build the debug APK.
13. verify it installs.
14. prepare ADB/logcat commands for physical BOOX testing.

Do not begin with caching, contextual narration, character recognition, or AI-director functionality.

---

# Agent Response Style

When working with the project owner:

* Explain what you are doing in plain English.
* When providing commands, assume Windows PowerShell unless stated otherwise.
* Give exact filenames when editing code.
* If multiple solutions exist, recommend one and briefly explain why.
* Avoid dumping large amounts of code without explaining where it belongs.
* When an error occurs, diagnose the cause before replacing large sections of code.
* Keep the project roadmap visible so development stays focused.

When a task is complete, summarize:

```text
What changed:
-

Why:
-

Files modified:
-

Build status:
-

What to test next:
-
```

---

# End Goal

The finished system should eventually make reading an EPUB in NeoReader feel closer to listening to a professionally narrated audiobook while still allowing the user to visually read and navigate normally on the BOOX.

The ideal experience is:

```text
Open book in NeoReader
        │
        ▼
Press Text-to-Speech
        │
        ▼
Spanky TTS automatically receives text
        │
        ▼
AI understands narration context
        │
        ▼
Natural, expressive speech begins
        │
        ▼
Continue reading normally in NeoReader
```

The experience should ultimately require very little interaction once configured.

**NeoReader handles reading. Spanky TTS handles narration.**
