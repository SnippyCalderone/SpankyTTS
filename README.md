# Spanky TTS

Spanky TTS is a custom Android Text-to-Speech engine for the **BOOX Go Color II** and **BOOX NeoReader**.

The project keeps NeoReader as the ebook reader while replacing conventional Android TTS with AI-generated narration.

The long-term goal is to make reading an EPUB in NeoReader feel closer to listening to a professionally narrated audiobook while preserving NeoReader's page layout, navigation, highlighting, bookmarks, and library experience.

---

## Current Status

The core end-to-end architecture now works on the physical BOOX.

Completed milestones:

- **Phase 1:** Android TTS engine / NeoReader integration
- **Phase 2A:** Live EPUB text anchoring
- **Phase 2B.1:** Local FastAPI backend + OpenAI TTS + real PCM playback in NeoReader
- **Phase 2B.2A:** Context-aware narration for reliably anchored requests, physically checked on BOOX
- **Larger-generation-unit feasibility:** Standalone chapter TTS experiment validated improved narration continuity and quality

Next design work:

- Source/audio alignment, deterministic request-to-audio mapping, and cached slicing of longer generated clips
- Pre-generation/look-ahead strategy with live per-request TTS fallback for cache misses or unverified slices

The current prototype can already read a real EPUB in NeoReader using OpenAI-generated speech.

The remaining issues are primarily narration quality and latency across NeoReader's small request boundaries.

The chapter experiment is separate from Android playback and the production backend. Its full-chapter audio can still omit the absolute final sentence even when the source text and block plan contain it. NeoReader continues to receive only audio for its exact current request through the proven live path.

---

## Current Architecture

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
FastAPI backend
      ↓
OpenAI gpt-4o-mini-tts
      ↓
Raw PCM audio
      ↓
Android SynthesisCallback
      ↓
NeoReader playback
```

NeoReader remains responsible for the visual reading experience.

Spanky TTS is responsible for narration.

---

## What Works Today

### Android / BOOX

Physically verified on a BOOX Go Color II:

- Spanky TTS installs as an Android `TextToSpeechService`.
- Android exposes it as a selectable TTS engine.
- NeoReader can invoke it directly.
- NeoReader book text reaches `onSynthesizeText()`.
- Stop/cancel behavior reaches `onStop()`.
- Real OpenAI-generated speech plays through NeoReader.

A controlled Android test also proved that Android preserves a single 493-character utterance as one synthesis request. The smaller chunks observed during ebook playback originate upstream from NeoReader.

### EPUB anchoring

Spanky can import the same EPUB being read in NeoReader and index it in reading order.

The indexer resolves:

```text
META-INF/container.xml
        ↓
OPF package
        ↓
manifest
        ↓
spine
        ↓
readable XHTML/HTML sections
```

Incoming NeoReader text is normalized and matched against the active EPUB.

The matcher supports:

- initial global establishment
- rolling forward tracking
- short-chunk local matching
- conservative ambiguity handling
- same-section jump recovery
- cross-section/global recovery
- confirmed cross-section re-anchoring

### OpenAI backend

A local Python/FastAPI backend now handles OpenAI communication.

Endpoints:

```text
GET /health
POST /tts
```

The backend uses:

```text
gpt-4o-mini-tts
```

and returns raw:

```text
24,000 Hz
PCM signed 16-bit little-endian
mono
```

The Android app delivers that PCM through `SynthesisCallback`.

### Cancellation

Cancellation is supported both:

- while PCM is being delivered to Android
- while the Android service is waiting on an in-flight backend request

Cancelled requests do not proceed through the normal `done()` path.

---

## Current Limitation

NeoReader frequently sends small fragments rather than complete narration-friendly paragraphs.

For example:

```text
"And of course,"
```

Phase 2B.1 deliberately maps:

```text
1 NeoReader request
=
1 backend request
=
1 OpenAI speech generation
```

This proves correctness, but it can create:

- slight pauses between fragments
- cadence resets
- punctuation that sounds too final
- inconsistent short-fragment delivery
- repeated generation latency

Phase 2B.2A supplies surrounding EPUB context when the current request has a
reliable anchor. BOOX testing found modest continuity improvement and no spoken
surrounding text. Separate generations still cause audible resets at some
request boundaries. The exact current NeoReader request remains the sole
speech input.

---

## Technology Stack

### Android

- Kotlin
- Android SDK
- `TextToSpeechService`
- `SynthesisCallback`
- AndroidX
- OkHttp 4.11.0
- `org.json.JSONObject`
- Gradle Kotlin DSL

### EPUB / anchoring

- EPUB ZIP parsing
- `container.xml`
- OPF manifest/spine resolution
- normalized text index
- rolling anchor matcher

### Backend

- Python 3
- FastAPI
- Uvicorn
- OpenAI Python SDK
- python-dotenv

### AI speech

- OpenAI Speech API
- `gpt-4o-mini-tts`
- current development voice: `cedar`

### Build

- Gradle 8.2.1
- Android Gradle Plugin 8.1.0
- JDK 17

### Development

- Windows 11
- Visual Studio Code
- Android Studio for SDK management
- ADB
- Git / GitHub

---

## Repository Structure

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
│           ├── layout/
│           │   └── activity_main.xml
│           └── xml/
│               └── tts_engine.xml
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── .env.example
│   ├── README.md
│   └── requirements.txt
│
├── gradle/
│   └── wrapper/
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

Local-only files such as `local.properties`, `backend/.env`, the Python virtual environment, and generated PCM/WAV test audio are excluded from Git.

---

## Building the Android App

From PowerShell in the repository root:

```powershell
.\gradlew.bat assembleDebug
```

Expected result:

```text
BUILD SUCCESSFUL
```

Debug APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

Install or replace it on the connected BOOX:

```powershell
adb devices
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Physical BOOX testing is preferred because NeoReader compatibility is a core requirement.

---

## Backend Setup

### 1. Create a virtual environment

```powershell
python -m venv backend\.venv
```

Activate it:

```powershell
backend\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -r backend\requirements.txt
```

### 3. Create the local environment file

```powershell
Copy-Item backend\.env.example backend\.env
```

Edit:

```text
backend/.env
```

and set:

```text
OPENAI_API_KEY=your_real_key_here
```

Never commit this file.

### 4. Start the backend

For PC-only testing:

```powershell
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

For BOOX LAN testing:

```powershell
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Current development Android configuration points to:

```text
http://<development-pc-ip>:8000
```

That address is a temporary LAN development constant and may need to be changed if the PC's local IP changes.

### 5. Health check

```powershell
Invoke-RestMethod http://<development-pc-ip>:8000/health
```

Expected body:

```json
{"status":"ok","service":"spanky-tts-backend"}
```

---

## Backend TTS Contract

Current Android request:

```json
{
  "text": "<exact current synthesis request>",
  "voice": "cedar",
  "instructions": "Read naturally as a professional audiobook narrator. Use natural pacing and expressive but restrained delivery."
}
```

When the EPUB anchor is reliable, Android may also include optional
`previous_context` and `following_context` fields (up to 240 characters each).
The backend uses those fields only to guide delivery; it sends only `text` as
the OpenAI speech input. Missing or ambiguous anchors keep the request above.

Successful response:

```text
HTTP 200
Content-Type: application/octet-stream
X-Audio-Sample-Rate: 24000
X-Audio-Encoding: pcm_s16le
X-Audio-Channels: 1
```

The response body is raw PCM bytes.

No base64 encoding is used.

---

## Security

The OpenAI API key must never be:

- hardcoded in Kotlin
- stored in Android resources
- committed to Git
- printed to logs
- transmitted from the BOOX

The key currently lives only in:

```text
backend/.env
```

The tracked template:

```text
backend/.env.example
```

contains no secret.

Current development HTTP access is limited to trusted LAN testing. The Android cleartext allowance and hardcoded local backend URL are temporary and should eventually be replaced by a safer configurable/HTTPS deployment.

---

## BOOX Development Settings

Settings used successfully during physical testing:

```text
Auto-start: ON
Freeze: OFF
Pause app activity if unused: OFF
Stay active in background: Unlimited
```

---

## Roadmap

### Phase 1 — COMPLETE

Android TTS integration and NeoReader compatibility.

### Phase 2A — COMPLETE

EPUB import, spine-aware indexing, normalized matching, live anchoring, and re-anchor recovery.

### Phase 2B.1 — COMPLETE

FastAPI backend, OpenAI PCM generation, BOOX LAN transport, Android callback delivery, live NeoReader speech, and cancellation.

### Phase 2B.2A — COMPLETE

Context-aware narration continuity.

Goal:

```text
surrounding EPUB context
        +
exact current NeoReader chunk
        ↓
better narration guidance
        ↓
speak ONLY current chunk
```

### Larger-generation-unit feasibility — VALIDATED / COMPLETE

The standalone [chapter TTS experiment](experiments/chapter_tts/README.md) generated Chapter Five as five coherent blocks. Listening found materially better audiobook continuity, pacing, and dialogue than tiny independent requests. The planner protects short non-final block tails and verifies an exact join back to the extracted chapter. Fidelity prompting improved isolated final-paragraph delivery, but a later full-chapter run still omitted the absolute final sentence. The experiment has no NeoReader playback integration.

### Phase 2B.2B — NEXT MILESTONE

Design and implement source/audio alignment, deterministic mapping, and cached audio slicing so each NeoReader request receives only its own verified audio span. Plan pre-generation and look-ahead, fallback to live per-request TTS on cache misses, and eventual chapter-boundary handling. Cached playback and alignment are not yet implemented.

### Later

- narration presets
- settings UI
- configurable backend
- cache management
- narration director
- dialogue/character awareness
- improved deployment/security

---

## Development Principles

1. Keep the project buildable after meaningful changes.
2. Make small, testable changes.
3. Test on the physical BOOX early.
4. Prefer ADB/logcat evidence over assumptions.
5. Preserve NeoReader as the reader.
6. Keep book text separate from narration instructions.
7. Never expose API credentials.
8. Do not let surrounding context accidentally become spoken text.
9. Preserve correct Android TTS callback and cancellation behavior.
10. Avoid premature complexity.

---

## Documentation

Detailed agent/development context:

```text
PROJECT_CONTEXT.md
```

Current implementation status and verified checkpoints:

```text
STATUS.md
```

Backend-specific setup:

```text
backend/README.md
```
