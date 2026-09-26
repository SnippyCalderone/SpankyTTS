# Spanky TTS — Development Status

**Last updated:** 2026-09-25

## Current Phase

**Phase 2B.1 COMPLETE — Live OpenAI TTS transport on the physical BOOX**

The project has now proven the full end-to-end path from BOOX NeoReader to the local FastAPI backend, through OpenAI `gpt-4o-mini-tts`, and back to Android as raw PCM audio.

The next active milestone is:

**Phase 2B.2A — Narration Continuity / Context-Aware Delivery**

The immediate goal is to improve tone, cadence, and continuity across NeoReader's small synthesis chunks without changing the exact text NeoReader asks Spanky TTS to speak.

---

## Current Known-Good Architecture

```text
BOOX NeoReader
      ↓
Android Text-to-Speech Framework
      ↓
SpankyTTSService
      ↓
Phase 2A EPUB anchor/matcher
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
NeoReader playback on BOOX
```

Current development backend:

```text
http://<development-pc-ip>:8000
```

This LAN URL and cleartext HTTP configuration are temporary development settings.

---

## Phase 1 — COMPLETE

### Android TTS Proof of Concept

Verified on the physical BOOX Go Color II:

- Spanky TTS installs successfully.
- Android recognizes Spanky TTS as a selectable TTS engine.
- BOOX NeoReader invokes `SpankyTTSService`.
- Real NeoReader book text reaches `onSynthesizeText()`.
- Valid PCM audio can be returned through `SynthesisCallback`.
- `onStop()` cancellation works.
- A controlled Android test sends exactly one 493-character `TextToSpeech.speak()` call.
- Spanky receives exactly one 493-character `SynthesisRequest`.
- Therefore Android itself preserves the long utterance.
- NeoReader is the component that performs the observed upstream chunking.

The original 440 Hz diagnostic tone was useful for Phase 1 but has now been replaced by real backend-generated speech.

---

## Phase 2A — COMPLETE

### Live EPUB Text Anchoring

Spanky can import an EPUB and use the incoming NeoReader text itself as a position anchor.

### EPUB indexing

The indexer now follows EPUB reading order using:

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

Latest validation fixture:

```text
The Reptile Room
package=content.opf
spine items=30
indexed spine sections=30
fallback=false
```

If package/spine parsing cannot produce a usable index, the indexer falls back to a broad HTML/XHTML scan rather than failing the import.

### Matcher behavior

Verified behavior includes:

- Initial global anchor establishment from distinctive incoming text.
- Rolling cursor tracking after establishment.
- Short-chunk tracking near the current cursor.
- Conservative handling of ambiguous short/common fragments.
- Same-section forward jump recovery.
- Cross-section/global re-anchor recovery.
- Pending cross-section re-anchor candidates that require confirmation from the following request before changing active section.
- Fresh re-establishment if the Android service/process is recreated.

### Known Phase 2A limitation

Extremely short or repeated text can still be ambiguous.

In those cases the matcher intentionally avoids guessing. A following distinctive request normally catches the cursor up.

This is acceptable for position tracking, but it matters for future audio caching/alignment work where every exact request range may eventually need deterministic mapping.

---

## Phase 2B.1 — COMPLETE

### FastAPI backend foundation

A Python backend now exists under:

```text
backend/
```

Implemented endpoints:

```text
GET /health
POST /tts
```

`GET /health` works without an OpenAI key.

`POST /tts`:

- accepts text
- accepts a voice
- accepts narration instructions
- uses fixed model `gpt-4o-mini-tts`
- requests raw PCM
- returns binary PCM directly
- does not use base64

Expected successful audio contract:

```text
Content-Type: application/octet-stream
X-Audio-Sample-Rate: 24000
X-Audio-Encoding: pcm_s16le
X-Audio-Channels: 1
```

Validation/error behavior includes:

- missing API key → controlled HTTP 503
- blank text → HTTP 400
- text over 5000 characters → HTTP 413
- OpenAI failure → sanitized HTTP 502
- no API key or authorization secret is logged

### OpenAI key handling

The OpenAI API key exists only in:

```text
backend/.env
```

The tracked template is:

```text
backend/.env.example
```

The Android app does **not** contain or transmit the OpenAI API key.

Git ignore rules cover local secrets/artifacts including:

```text
backend/.env
backend/.venv/
backend/*.pcm
backend/*.wav
backend/**/__pycache__/
backend/**/*.pyc
```

### BOOX → backend LAN connectivity

Physically verified from the BOOX browser:

```text
http://<development-pc-ip>:8000/health
```

returned HTTP 200.

Development networking currently uses:

- Uvicorn bound to `0.0.0.0:8000`
- Windows home network profile set to Private
- inbound TCP 8000 allowed on the Private firewall profile
- Android cleartext HTTP temporarily enabled for LAN development

### Android backend integration

`SpankyTTSService` now sends one backend request for each Android/NeoReader synthesis request.

Current request shape:

```json
{
  "text": "<exact incoming synthesis request text>",
  "voice": "cedar",
  "instructions": "Read naturally as a professional audiobook narrator. Use natural pacing and expressive but restrained delivery."
}
```

The service:

- preserves Phase 2A anchor processing
- posts to the development backend
- validates the backend response
- starts `SynthesisCallback` at 24 kHz PCM16 mono
- splits PCM into chunks no larger than `callback.maxBufferSize`
- checks cancellation while delivering audio
- calls `done()` only after successful non-cancelled delivery
- uses `callback.error()` for real failures
- does not fall back to the old test tone

### Physical Phase 2B.1 results

Verified on the BOOX:

#### Controlled 493-character test

- Real OpenAI-generated speech played through the BOOX.
- The full controlled paragraph completed successfully.
- The backend returned valid raw PCM.
- Android callback delivery completed successfully.

A repeated controlled test was cancelled during playback and:

- `onStop()` fired
- cancellation state was set
- PCM delivery stopped
- the request did not continue to normal completion

#### NeoReader live book test

The Reptile Room was re-imported and NeoReader TTS was started directly at Chapter 5.

Verified:

- Chapter heading went through real backend TTS.
- First distinctive sentence established the Chapter 5 EPUB anchor.
- Subsequent chunks tracked normally.
- Every tested NeoReader chunk was sent to the backend and returned real OpenAI PCM.
- Speech was audible in NeoReader.
- Stopping NeoReader TTS while a request was in flight cancelled the active backend call cleanly.

### Observed latency

The controlled 493-character backend generations took several seconds.

During the live NeoReader run, small chunks commonly completed in roughly:

```text
~0.7–1.8 seconds
```

with occasional slower requests around:

```text
~2.8 seconds
```

This is now a quality/latency optimization problem, not a transport or compatibility problem.

---

## Current Quality Limitation

NeoReader sends many relatively small fragments, including text such as:

```text
"And of course,"
```

Phase 2B.1 intentionally treats each incoming fragment as its own independent OpenAI speech request.

That produces correct speech, but the model lacks the surrounding sentence/scene context when performing each chunk.

Observed effects:

- small pauses between some fragments
- cadence resets at request boundaries
- commas can sound too final
- tone can vary more than desired
- each fragment incurs its own generation latency

This behavior is expected from the current one-request/one-generation prototype.

---

## Phase 2B.2A — NEXT

### Narration Continuity / Context-Aware Delivery

Goal:

> Give the speech model enough surrounding EPUB context to perform the **current NeoReader chunk** naturally, while ensuring that only the current requested text is spoken.

Conceptually:

```text
Previous EPUB context
Current NeoReader request
Following EPUB context
        ↓
Narration-aware instructions/context
        ↓
OpenAI TTS
        ↓
Speak ONLY current NeoReader request
```

Immediate design questions:

1. What amount of prior/following EPUB context should be supplied?
2. Should Android send raw surrounding text to the backend, anchor metadata, or both?
3. How should the backend clearly separate context from text-to-speak?
4. How do we guarantee surrounding context is never spoken?
5. How much does context improve cadence on short fragments?
6. What latency/cost change does context introduce?

### First validation target

Use known awkward fragments such as:

```text
"And of course,"
```

and compare:

- Phase 2B.1 isolated delivery
- Phase 2B.2A context-aware delivery

Success means the fragment sounds like part of the surrounding sentence rather than a standalone utterance.

---

## Phase 2B.2B — LATER

### Latency / Prefetch / Cache / Alignment

After contextual delivery is proven, address generation gaps.

Likely topics:

- pre-generation
- look-ahead/prefetch
- local audio caching
- deterministic cache keys
- exact request-to-audio mapping
- larger natural generation units
- forced alignment or timestamp-based audio slicing if larger clips are generated

Important constraint:

A larger pre-generated paragraph cannot simply be returned for a smaller NeoReader request. Android/NeoReader still expects audio corresponding to the current synthesis request.

Larger cached clips therefore require either:

- generation at compatible request granularity, or
- accurate text/audio alignment and slicing

Do not hide this constraint with naive request aggregation.

---

## BOOX Settings Used During Validation

```text
Auto-start: ON
Freeze: OFF
Pause app activity if unused: OFF
Stay active in background: Unlimited
```

These settings helped keep the custom TTS service available during NeoReader testing.

---

## Known-Good Commands

### Android build

```powershell
.\gradlew.bat assembleDebug
```

Expected:

```text
BUILD SUCCESSFUL
```

APK:

```text
app\build\outputs\apk\debug\app-debug.apk
```

### Install / replace APK

```powershell
adb devices
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

### Logcat

```powershell
adb logcat -c
adb logcat SpankyTTS:I AndroidRuntime:E *:S
```

Saved diagnostic log:

```powershell
adb logcat SpankyTTS:I AndroidRuntime:E *:S | Tee-Object -FilePath phase2_tts_live.txt
```

### Backend setup

```powershell
backend\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

### Health check

```powershell
Invoke-RestMethod http://<development-pc-ip>:8000/health
```

---

## Known-Good Toolchain

```text
OS: Windows 11
JDK: 17
Gradle: 8.2.1
Android Gradle Plugin: 8.1.0
Language: Kotlin
Android package: com.snippycalderone.spankytts
Backend: Python / FastAPI / Uvicorn
Speech model: gpt-4o-mini-tts
Android HTTP client: OkHttp 4.11.0
```

---

## Repository Checkpoint

The Phase 2B.1 implementation has been committed and pushed.

Current checkpoint includes:

- Phase 2A EPUB anchoring
- spine-aware EPUB indexing
- conservative re-anchor confirmation
- FastAPI backend
- secure local API-key handling
- OpenAI PCM generation
- BOOX LAN connectivity
- Android backend integration
- real NeoReader OpenAI narration
- cancellation support

---

## Current Blockers

None preventing continued development.

The fundamental end-to-end architecture is proven.

---

## Next Action

Design and implement **Phase 2B.2A — context-aware narration continuity** without breaking:

- Phase 2A anchoring
- exact current-request speech
- Android TTS callback lifecycle
- cancellation
- backend key isolation
- current successful BOOX transport
