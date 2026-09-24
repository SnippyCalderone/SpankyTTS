Spanky TTS — Development Status

Current Phase

Phase 1 COMPLETE — Android TTS Proof of Concept

Current Objective

Phase 1 objective has been achieved: Spanky TTS operates as a selectable Android Text-to-Speech engine on the BOOX Go Color II and successfully receives synthesis requests from NeoReader.

Verified Phase 1 flow:

NeoReader
    ↓
Android TTS Framework
    ↓
Spanky TTS
    ↓
Receive synthesis request
    ↓
Log incoming text
    ↓
Return valid test audio

OpenAI speech generation remains intentionally deferred until Phase 2 architecture work is defined.

Current Build Status

BUILD SUCCESSFUL

Known-good command:

.\gradlew.bat assembleDebug

Generated APK:

app\build\outputs\apk\debug\app-debug.apk

Completed Milestones

Repository / Documentation

GitHub repository created

Repository cloned locally

PROJECT_CONTEXT.md created

STATUS.md created

README.md established

.gitignore configured

Development Environment

Windows development environment configured

Visual Studio Code selected as primary editor

Android Studio installed for SDK management

JDK 17 installed

JAVA_HOME configured

Android SDK installed

ANDROID_HOME configured

ANDROID_SDK_ROOT configured

Android SDK Platform-Tools installed

Android SDK Command-line Tools installed

sdkmanager verified

Official Android SDK adb verified

Obsolete Touch Portal ADB installation removed

Gradle Setup

Android project scaffolded

Package established as com.snippycalderone.spankytts

Android Gradle Plugin configured

Gradle 8.2.1 selected

Project-local Gradle Wrapper generated

gradlew created

gradlew.bat created

gradle-wrapper.jar generated

gradle-wrapper.properties generated

Global Gradle dependency avoided

Temporary bootstrap Gradle distribution removed/ignored

Android SDK / Build Configuration

Android SDK path configured through local.properties

local.properties ignored by Git

AndroidX enabled

Current gradle.properties includes:

android.useAndroidX=true
android.enableJetifier=true

Google Maven repository added

Maven Central added

Gradle Plugin Portal added

Dependency repositories configured correctly

Android Manifest

Obsolete manifest package= declaration removed

Application namespace moved to Gradle configuration

MainActivity configured

MainActivity has explicit android:exported

SpankyTTSService registered

TTS service intent filter added

Erroneous TTS service binding permission attempt removed; final working manifest does not rely on a TTS binding permission declaration

SpankyTTSService has explicit android:exported

TTS engine metadata resource configured

TTS Engine Metadata

tts_engine.xml created

Invalid android:defaultLocale configuration removed

XML validated successfully

Kotlin TTS Service

SpankyTTSService.kt currently extends:

TextToSpeechService

Required Android service methods now compile:

onIsLanguageAvailable

onLoadLanguage

onGetLanguage

onSynthesizeText

onStop

Current implementation is intentionally diagnostic and Phase 1-ready.

Current Project State

The project now compiles successfully from the command line.

Current architecture:

Android Application
        │
        ├── MainActivity
        │
        └── SpankyTTSService
                │
                └── TextToSpeechService

SpankyTTSService now contains working local diagnostic synthesis with thread-safe cancellation handling.

No OpenAI API calls have been implemented yet.

No narration caching has been implemented.

No contextual narration has been implemented.

No character detection has been implemented.

This is intentional.

Phase 1 Completion Summary

Verified physical BOOX results:

Spanky TTS builds and installs successfully on the BOOX.

Android recognizes com.snippycalderone.spankytts/.SpankyTTSService as a real TTS engine.

"Spanky TTS" appears in Android Text-to-speech output settings and can be selected.

BOOX NeoReader successfully invokes SpankyTTSService.

Real book text from NeoReader was captured in onSynthesizeText().

PCM audio synthesis works and produces audible output.

NeoReader was observed sending many relatively small text chunks.

Controlled Android-vs-NeoReader test:

MainActivity sent exactly ONE TextToSpeech.speak() call.

The test string was exactly 493 characters.

SpankyTTSService received exactly ONE SynthesisRequest.

The service received the same complete 493-character string.

Therefore the Android TTS framework preserves the long utterance.

The previously observed small chunks originate upstream from NeoReader/its TTS integration, not from SpankyTTSService or normal Android TTS utterance splitting.

Cancellation test:

A temporary slow synthesis diagnostic was used to keep synthesis active.

TextToSpeech.stop() caused SpankyTTSService.onStop() to execute.

onStop() set the AtomicBoolean cancellation flag.

The active synthesis loop detected cancellation.

The cancelled request exited without callback.done().

The temporary slow/10-second diagnostic behavior has since been removed.

Thread-safe AtomicBoolean cancellation handling remains in the service.

Normal local test synthesis is restored to approximately one second of 440 Hz PCM.

Current normal diagnostic synthesis:

440 Hz

16 kHz

PCM 16-bit

mono

approximately 1 second

respects callback.maxBufferSize

cancellation checked during synthesis and again before callback.done()

Current Task

Phase 1 cleanup and verification are complete.

No code changes are required for additional Phase 1 validation at this time.

Required Phase 1 Logging

Each incoming synthesis request records:

Request number
Timestamp
Character count
Locale
Speech rate
Pitch
Incoming text

Example:

SpankyTTS: SYNTHESIS REQUEST #14

Characters: 183
Locale: en-US
Speech Rate: 1.0
Pitch: 1.0

Text:
"The room was completely silent..."

Cancellation should also log:

SpankyTTS: onStop()

The purpose of this logging is not just debugging.

It is now used for ongoing diagnostics and for Phase 2 request-pattern analysis.

Phase 1 verification already established that NeoReader sends relatively small synthesis requests, while Android preserved a controlled 493-character utterance intact.

Therefore, the observed small chunking originates upstream from NeoReader/its TTS integration.

Major Unknown (Phase 2)

How best to aggregate NeoReader's small requests into narration-quality units for OpenAI while preserving responsiveness and correctness.

## Phase 1 Diagnostics Implemented

- Detailed logging of each synthesis request in onSynthesizeText (sequential ID, timestamp, text, char count, locale, rate, pitch, thread)
- Logging cancellation events in onStop
- Local PCM test tone (440 Hz sine wave, 1 s duration, 16 kHz sample rate, 16-bit mono) returned via SynthesisCallback
- Callback lifecycle: start(sampleRate, audioFormat, channelCount) → audioAvailable(buffer, length) chunks → done() for completed requests
- Cancellation lifecycle: onStop() sets the AtomicBoolean cancellation flag, synthesis detects the flag and exits, and callback.done() is not called for a cancelled request

## Build Status

- Project builds successfully with `.\gradlew.bat assembleDebug` after changes

## Next Phase

Phase 2 begins with architecture design for the bridge between NeoReader request patterns and OpenAI speech generation.

Phase 2 architecture topics to define:

request aggregation/buffering

reconstructing useful sentence/paragraph-sized narration units

latency versus context tradeoffs

handling NeoReader prefetch/queued requests

cancellation with buffered/in-flight requests

avoiding one OpenAI API call for every tiny NeoReader phrase

maintaining natural narration continuity

determining when buffered text is ready to send to OpenAI

Do not implement this phase yet; design and validation planning come first.

Phase 2 — OpenAI Speech Integration (after bridge design)

Target architecture:

NeoReader
    ↓
SpankyTTSService
    ↓
OpenAI Speech API
    ↓
PCM Stream
    ↓
SynthesisCallback
    ↓
NeoReader Playback

Phase 3 — Usability

Potential work:

narration presets

improved settings UI

voice previews

better error handling

network state handling

retry behavior

configurable buffering

API usage information

Phase 4 — Local Audio Cache

Goals:

avoid repeated API charges

improve replay speed

cache identical synthesis requests

invalidate cache when relevant voice/settings change

Potential cache identity:

text
+
provider
+
model
+
voice
+
instructions
+
speech settings

Phase 5 — Context Awareness

Potential rolling context:

Previous request
Previous request
Current request
        ↓
Narration analysis
        ↓
Speak current request only

Previous text must never accidentally be synthesized again.

Phase 6 — AI Narration Director

Potential future analysis:

Mood
Pacing
Energy
Emotion
Dialogue intensity
Pause behavior

The director should generate narration instructions while preserving the original book text.

Phase 7 — Character Awareness

Experimental future goal:

identify recurring speakers

maintain consistent character delivery

avoid random voice switching

distinguish narration from dialogue

This phase remains speculative until NeoReader request behavior is known.

Current Blockers

None.

Phase 1 objectives are complete and verified.

Known Good Toolchain

OS:
Windows 11

JDK:
17

Gradle:
8.2.1

Android Gradle Plugin:
8.1.0

Language:
Kotlin

Package:
com.snippycalderone.spankytts

Last Known Good Build

Command:

.\gradlew.bat assembleDebug

Result:

BUILD SUCCESSFUL

Next Action

Define and review the Phase 2 request-aggregation bridge design before implementing OpenAI speech calls for NeoReader playback.