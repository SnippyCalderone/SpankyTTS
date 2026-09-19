# Spanky TTS

Spanky TTS is a custom Android Text-to-Speech engine designed primarily for the **BOOX Go Color II** and **BOOX NeoReader**.

The project aims to preserve NeoReader as the visual ebook-reading experience while replacing conventional Android TTS with significantly more natural, expressive AI-generated narration.

The long-term goal is to make reading an EPUB in NeoReader feel closer to listening to a professionally narrated audiobook without requiring a separate ebook-reader application.

---

# Project Goal

Spanky TTS is **not** intended to replace NeoReader.

NeoReader remains responsible for:

- EPUB rendering
- page layout
- fonts
- page navigation
- highlighting
- bookmarks
- ebook library management
- reading position
- visual reading experience

Spanky TTS is responsible only for **speech generation and narration**.

The intended architecture is:

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
AI Speech Provider
    │
    ▼
Generated PCM Audio
    │
    ▼
Android SynthesisCallback
    │
    ▼
NeoReader Playback
```

The first planned AI speech provider is the **OpenAI Speech API**.

---

# Why This Project Exists

Traditional Android TTS engines usually provide only basic controls such as:

- voice
- speech rate
- pitch
- locale

That is sufficient for accessibility and basic text reading, but it does not provide the kind of narration expected from an audiobook.

Spanky TTS is intended to eventually support:

- natural conversational cadence
- variable pacing
- scene-aware delivery
- emotional tone
- better pauses
- expressive dialogue
- consistent narration style
- context-aware emphasis
- narration presets
- eventually, character-aware delivery

The core idea is:

```text
Normal Android TTS

Text
 ↓
Voice
 ↓
Speech


Spanky TTS

Text
 ↓
Context / narration instructions
 ↓
AI speech model
 ↓
Expressive narration
```

---

# Primary Target

## Device

**BOOX Go Color II**

## Reader

**BOOX NeoReader**

## Android Integration

Spanky TTS is implemented as an Android:

```text
TextToSpeechService
```

This allows Android and applications such as NeoReader to treat Spanky TTS as a normal selectable system TTS engine.

The user should eventually be able to:

```text
Open book in NeoReader
        ↓
Start Text-to-Speech
        ↓
NeoReader sends text to Android
        ↓
Android routes request to Spanky TTS
        ↓
Spanky TTS generates AI narration
        ↓
Audio plays while NeoReader remains open
```

---

# Technology Stack

## Application

- Kotlin
- Android SDK
- Android `TextToSpeechService`
- Android `SynthesisCallback`
- Gradle Kotlin DSL
- AndroidX

## Build System

- Gradle Wrapper
- Gradle 8.2.1
- Android Gradle Plugin 8.1.0
- JDK 17

## Development Environment

- Windows 11
- Visual Studio Code
- VS Code AI coding agent
- Android Studio for Android SDK management
- Android Debug Bridge (`adb`)
- Git
- GitHub

## Planned Networking / Storage

- OkHttp
- Kotlin serialization
- Android DataStore
- secure local credential storage
- local synthesized-audio cache

## Planned AI Provider

Initial provider:

```text
OpenAI Speech API
```

Initial speech model:

```text
gpt-4o-mini-tts
```

---

# Current Project Structure

```text
SpankyTTS/
│
├── app/
│   ├── build.gradle.kts
│   ├── proguard-rules.pro
│   │
│   └── src/main/
│       ├── AndroidManifest.xml
│       │
│       ├── java/com/snippycalderone/spankytts/
│       │   ├── MainActivity.kt
│       │   └── SpankyTTSService.kt
│       │
│       └── res/
│           ├── layout/
│           │   └── activity_main.xml
│           │
│           └── xml/
│               ├── preferences.xml
│               └── tts_engine.xml
│
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
│
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── gradlew
├── gradlew.bat
├── PROJECT_CONTEXT.md
├── STATUS.md
├── README.md
└── .gitignore
```

`local.properties` exists locally for the Android SDK path but is excluded from Git because it contains machine-specific configuration.

---

# Building the Project

From PowerShell in the repository root:

```powershell
.\gradlew.bat assembleDebug
```

A successful build should finish with:

```text
BUILD SUCCESSFUL
```

The generated debug APK is located at:

```text
app\build\outputs\apk\debug\app-debug.apk
```

---

# Installing on an Android Device

Once USB debugging is enabled and the device is visible to ADB:

```powershell
adb devices
```

The debug APK can be installed with:

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Physical BOOX testing is preferred over emulator-only testing because NeoReader compatibility is one of the primary goals of the project.

---

# Phase 1 — Android TTS Proof of Concept

## Goal

Prove the fundamental Android integration before adding AI speech generation.

The Phase 1 flow is:

```text
NeoReader
    ↓
Android TTS Framework
    ↓
SpankyTTSService
    ↓
Receive synthesis request
    ↓
Log request
    ↓
Return valid audio
```

Phase 1 must prove that:

- Android recognizes Spanky TTS as a TTS engine
- the BOOX can select Spanky TTS
- NeoReader can use Spanky TTS
- `SpankyTTSService` receives synthesis requests
- incoming text can be inspected
- stop/cancel requests work
- valid audio can be returned through `SynthesisCallback`

---

# Why NeoReader Request Logging Matters

One major unknown is how NeoReader divides book text into Android TTS requests.

NeoReader may send:

```text
Sentence
```

or:

```text
Paragraph
```

or:

```text
Page
```

or larger blocks.

That behavior will determine how much context Spanky TTS receives naturally.

Phase 1 logging should capture:

- incoming text
- character count
- locale
- speech rate
- pitch
- timestamp
- request order
- cancellation events
- errors

Example:

```text
SpankyTTS: SYNTHESIS REQUEST

Characters: 247
Locale: en-US
Speech Rate: 1.0
Pitch: 1.0

Text:
"Kvothe looked toward the window. Outside, the wind had begun to rise..."
```

---

# Phase 2 — OpenAI Speech Integration

After basic NeoReader compatibility is verified, Spanky TTS will begin sending incoming text to the OpenAI Speech API.

Expected flow:

```text
NeoReader
    ↓
SpankyTTSService
    ↓
OpenAI Speech API
    ↓
PCM audio
    ↓
SynthesisCallback
    ↓
Playback
```

Initial settings will likely include:

- OpenAI API key
- voice
- playback speed
- narration instructions
- test voice button

Example narration instructions:

```text
Narrate as a professional audiobook narrator.

Use natural cadence and varied pacing.

Allow dialogue to carry more emotion than exposition.

Use subtle emotional changes appropriate to the scene.

Slow slightly during atmospheric passages.

Respect punctuation and paragraph boundaries with natural pauses.

Avoid exaggerated theatrical delivery.

Maintain a consistent narrator voice.
```

The original book text should remain unchanged.

Narration instructions affect delivery, not content.

---

# Phase 3 — Narration Presets

Possible narration presets:

- Fantasy Audiobook
- Thriller
- Science Fiction
- Nonfiction
- Technical
- Conversational
- Dramatic
- Custom

A preset should primarily modify narration instructions rather than create separate code paths.

---

# Phase 4 — Local Audio Cache

Repeated text should not require repeated API synthesis.

A future cache key may include:

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
speech settings
```

Expected flow:

```text
Incoming text
      ↓
Generate cache key
      ↓
Cached?
   /       \
 Yes       No
  ↓         ↓
Play      OpenAI
            ↓
          Save
            ↓
          Play
```

Possible cache controls:

- maximum cache size
- clear cache
- cache statistics
- automatic cleanup

---

# Phase 5 — Context Buffer

If NeoReader sends only small text chunks, Spanky TTS may maintain a rolling history.

Example:

```text
Previous:
"I thought you'd left."

Previous:
She wouldn't look at him.

Current:
"I almost did."
```

Previous text would be used only to understand context.

Only the current request would be spoken.

This could improve:

- pacing
- emotional continuity
- dialogue delivery
- scene awareness

---

# Phase 6 — AI Narration Director

A separate AI analysis step may eventually determine how the current passage should be performed.

Example:

```text
Mood: tense
Energy: low
Pace: slightly slow
Emotion: restrained suspicion
Dialogue intensity: subtle
Pause behavior: deliberate
```

Architecture:

```text
NeoReader Text
      ↓
Context Buffer
      ↓
AI Narration Director
      ↓
Narration Instructions
      ↓
AI Speech Model
      ↓
Audio
```

The director should analyze the text without rewriting the book.

---

# Phase 7 — Character Awareness

A later experimental phase may attempt to maintain consistent character narration profiles.

Example:

```text
Narrator
→ mature / neutral / controlled

Character A
→ younger / confident / energetic

Character B
→ quiet / reserved / deliberate
```

Character handling will not be implemented until:

- NeoReader request behavior is understood
- base TTS is reliable
- latency is acceptable
- narration context works reliably

---

# Security

API credentials must never be:

- hardcoded in Kotlin
- committed to Git
- stored in public configuration files
- printed to logs

Bad:

```kotlin
val apiKey = "sk-proj-..."
```

Future API credentials should be entered through the app and stored securely on the device.

---

# Non-Goals

Spanky TTS is not intended to become:

- an EPUB reader
- an EPUB parser
- an ebook library manager
- a replacement for NeoReader
- a web application
- a cloud backend
- a multi-user service
- a subscription platform

The project should stay focused on:

> **High-quality AI narration through Android's existing TTS framework.**

---

# Development Principles

1. Keep the project buildable after major changes.
2. Make small, testable changes.
3. Test on the physical BOOX early.
4. Use ADB/logcat instead of assumptions.
5. Do not overengineer future phases prematurely.
6. Keep Kotlin understandable and maintainable.
7. Protect API credentials.
8. Prefer the project-local Gradle Wrapper over global Gradle installations.
9. Treat NeoReader compatibility as a hard requirement.
10. Keep the reader and speech engine responsibilities separated.

---

# Documentation

Long-term architecture and agent instructions:

```text
PROJECT_CONTEXT.md
```

Current development progress:

```text
STATUS.md
```

---

# Current Build Status

The Android project currently builds successfully with:

```powershell
.\gradlew.bat assembleDebug
```

Current result:

```text
BUILD SUCCESSFUL
```

The next major milestone is physical-device testing on the BOOX Go Color II.