# Spanky TTS — Development Status

**Last updated:** 2026-10-14

## Current Phase

**Phase 2B.1 COMPLETE — Live OpenAI TTS transport on the physical BOOX**

The project has now proven the full end-to-end path from BOOX NeoReader to the local FastAPI backend, through OpenAI `gpt-4o-mini-tts`, and back to Android as raw PCM audio.

**Phase 2B.2A COMPLETE — context-aware delivery is physically validated on the BOOX, with modest continuity gains and a known request-boundary limitation.**

**Larger-generation-unit feasibility milestone VALIDATED / COMPLETE.** A separate chapter TTS experiment showed that longer coherent generation materially improves continuity and audiobook quality. It does not change NeoReader playback. The next milestone is source/audio alignment and cached slicing so each NeoReader request receives only its corresponding audio span.

The current live per-request TTS path remains the fallback and safety path. A generative TTS edge case remains: the model can omit text at the absolute end of a final block or chapter.

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

Development backend (set the PC address in the ignored root `local.properties`
as `SPANKY_TTS_BACKEND_URL=http://<development-pc-ip>:8000/tts` before building):

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

During prior physical testing, the BOOX browser accessed the configured LAN
health endpoint:

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

## Phase 2B.2A — COMPLETE

### Narration Continuity / Context-Aware Delivery

Implementation checkpoint: the matcher exposes a
reliable current-fragment range, Android extracts up to 240 characters of
original EPUB text on each side, and the backend places those optional context
fields in delivery instructions while sending only the exact request as speech
input. Missing or ambiguous matches retain context-free delivery. Android unit
tests, backend mocked tests, and `assembleDebug` pass.

Initial physical BOOX comparison (2026-09-25): baseline and context runs were
logged and compared by listening. In the context run, 64 of 73 requests used EPUB context,
72 delivered PCM successfully, and one stopped cleanly during an in-flight
backend request; no backend errors appeared. The exact 15-character
"And of course," request had context on both sides. The listener reported it
was a little better, and "and they'd had plenty" was noticeably better, but
tone, cadence, and pace still reset at some comma boundaries. "Mr." and "Poe"
arrived in separate NeoReader requests and sounded especially discontinuous.
This is an observed quality limit of independent per-fragment generation, not
a transport failure. Cancellation during PCM delivery was checked twice with
the updated build's 493-character controlled test. Both runs reached
`callback.start()` and passed multiple PCM buffers before Stop.
`audioAvailable()` returned `-1` immediately before `onStop()`; the service
exited without `done()`. The existing log labels that callback return as an
error, though the timing is consistent with the client stop. The listener
confirmed that the context run spoke only words NeoReader requested; no
surrounding EPUB words were heard. This completes the scoped context-delivery
milestone. Separate generations still cause audible resets, especially when
NeoReader splits "Mr." from "Poe".

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

Resolved design choices and observations:

1. Android supplies up to 240 characters of original EPUB text on either side when the current match is reliable.
2. The backend receives separate `previous_context` and `following_context` fields; only the exact NeoReader request is OpenAI speech input.
3. The physical comparison found some improvement and no spoken surrounding text, but independent calls still reset delivery.
4. The context run repeated about 29,917 context characters across 73 requests, alongside 3,348 characters of speech input. These are character counts, not billed tokens.

### First validation target

Use known awkward fragments such as:

```text
"And of course,"
```

and compare:

- Phase 2B.1 isolated delivery
- Phase 2B.2A context-aware delivery

The listener found "And of course," a little better and another first-sentence
fragment noticeably better. Full audiobook-like continuity remains a later
architecture problem.

---

## Larger-generation-unit feasibility — VALIDATED / COMPLETE

The standalone `experiments/chapter_tts/` utility extracts EPUB chapters and generates larger narration blocks without using Android or the production `/tts` endpoint. Chapter Five of *The Reptile Room* was generated as five blocks. Listening comparisons found materially better continuity, pacing, dialogue transitions, and overall audiobook quality than tiny independent NeoReader requests. Generation speed made future pre-generation and caching practical to investigate.

The planner preserves paragraph boundaries where practical, moves a terminal paragraph of at most 120 characters from a non-final block to the next block when safe, and asserts that joining all blocks reproduces the extracted chapter exactly. The profile now includes text and ending fidelity instructions plus stronger scene and dialogue guidance. In the second full chapter run, the middle-of-chapter omissions were resolved, but the absolute final sentence was still absent from the audio. The sentence was present in the extracted and planned text. Isolated tests spoke it when real following EPUB text made it non-terminal and when explicit fidelity instructions were added to the short final paragraph; neither result solves terminal omission in a full final block.

This milestone validates larger natural generation units, not text/audio alignment, cached playback, or chapter-boundary handling. NeoReader still uses the live per-request path and must receive audio only for the exact current synthesis request.

---

## Phase 2B.2B — NEXT MILESTONE

### Source/audio alignment, cached slicing, and pre-generation

The feasibility question for larger generation units has been answered positively. Design and implement a mapping from exact EPUB source spans to verified audio spans before serving any part of a longer clip to NeoReader.

Required design work:

- source/audio alignment with checks for omitted beginning and ending text
- deterministic source-to-audio mapping and cache keys tied to text, model, voice, instructions, and relevant settings
- cached audio slicing for the exact current NeoReader request
- pre-generation and look-ahead strategy, including cache misses and fallback to live per-request TTS
- eventual chapter-boundary handling, including the unresolved terminal-position omission

Important constraint:

A larger pre-generated paragraph cannot simply be returned for a smaller NeoReader request. Android/NeoReader still expects audio corresponding to the current synthesis request.

Larger cached clips require accurate text/audio alignment and slicing before playback integration. If a verified slice is unavailable, use the existing live per-request TTS path. Do not hide this constraint with naive request aggregation.

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
Invoke-RestMethod 'http://<development-pc-ip>:8000/health'
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

Design and implement source/audio alignment and cached slicing as the next separate milestone, then validate exact request-to-audio mapping before changing NeoReader playback. Preserve:

- Phase 2A anchoring
- exact current-request speech
- Android TTS callback lifecycle
- cancellation
- backend key isolation
- current successful BOOX transport
- live per-request TTS as fallback for cache misses or unverified audio
