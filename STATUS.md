Spanky TTS — Development Status

Current Phase

Phase 1 — Android TTS Proof of Concept

Current Objective

Prove that Spanky TTS can operate as a selectable Android Text-to-Speech engine on the BOOX Go Color II and receive synthesis requests from NeoReader.

The immediate target is:

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

OpenAI speech generation is deliberately being postponed until the underlying Android TTS integration is proven.

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

TTS service binding permission added

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

Current implementation is still intentionally minimal.

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

SpankyTTSService currently contains placeholder behavior.

No OpenAI API calls have been implemented yet.

No narration caching has been implemented.

No contextual narration has been implemented.

No character detection has been implemented.

This is intentional.

Current Task

The next development task is to make the Android TTS engine useful enough for physical-device testing.

Implement:

detailed request logging

valid synthesis callback behavior

stop/cancel logging

simple proof-of-concept audio generation

engine readiness/error handling

Required Phase 1 Logging

Each incoming synthesis request should eventually record:

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

It is required to determine how NeoReader divides text into Android TTS requests.

Major Unknown

We do not yet know whether NeoReader sends:

Sentence

Paragraph

Page

or:

Multiple paragraphs

This is one of the most important Phase 1 discoveries.

The result will strongly affect:

context buffering

narration prompting

latency strategy

caching

scene analysis

future character awareness

Next Major Milestone

BOOX Physical-Device Test

Planned flow:

Build APK
    ↓
Connect BOOX with ADB
    ↓
Install app-debug.apk
    ↓
Open Android TTS settings
    ↓
Verify Spanky TTS appears
    ↓
Select Spanky TTS
    ↓
Open NeoReader
    ↓
Start TTS
    ↓
Inspect logcat

Useful ADB commands will likely include:

adb devices

and:

adb logcat

Eventually filtered logging may use something like:

adb logcat | findstr SpankyTTS

Phase 1 Acceptance Criteria

Phase 1 is complete only when:

APK installs successfully on BOOX

Android recognizes Spanky TTS as a TTS engine

Spanky TTS appears in Android TTS settings

Spanky TTS can be selected as preferred engine

NeoReader recognizes the engine

NeoReader calls onSynthesizeText

Incoming NeoReader text appears in logs

Request chunk size is understood

Valid audio is returned

Speech is audible

onStop responds correctly

No crashes occur during basic reading

No API credentials are present in source control

Phase 2 — OpenAI Speech Integration

Do not begin until the Phase 1 Android integration is verified.

Planned features:

OpenAI API client

gpt-4o-mini-tts

API key settings

voice selector

narration instructions

playback speed

Test Voice button

PCM response handling

streaming through SynthesisCallback

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

The project currently builds successfully.

The next work is functional Android TTS implementation and physical BOOX testing.

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

Implement request logging and simple synthesis behavior in:

app/src/main/java/com/snippycalderone/spankytts/SpankyTTSService.kt

Then rebuild and prepare the first APK for physical BOOX testing.