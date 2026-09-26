# Spanky TTS — Codex Repository Instructions

## Project Orientation

This is an existing project. Do not treat it as a greenfield Android application.

Use the project documentation selectively:

- Read `STATUS.md` to determine the current milestone, verified progress, and next action.
- Read `PROJECT_CONTEXT.md` when a task affects architecture, Android TTS behavior, EPUB anchoring, backend/OpenAI integration, networking, audio handling, or phase boundaries.
- Read `README.md` for repository structure, setup, build, backend, and usage information.

Do not repeatedly reread every documentation file for trivial edits.

## Source of Truth

Documentation describes the intended architecture and verified project history.

For implementation details, inspect the current source code before changing it.

If documentation and code disagree, report the discrepancy rather than silently choosing one.

## Current Project State

- Phase 1 is complete.
- Phase 2A is complete.
- Phase 2B.1 is complete and physically validated on the BOOX Go Color II.
- Current work begins with **Phase 2B.2A — Context-Aware Narration Continuity**.

Do not implement later cache, prefetch, alignment, narration-director, or character-awareness work unless the requested task specifically calls for it.

## Important Constraints

- NeoReader remains the ebook reader.
- Spanky TTS is an Android `TextToSpeechService`.
- Preserve the existing Phase 2A EPUB anchoring system unless the task specifically concerns anchoring.
- Preserve the working Phase 2B.1 backend/PCM/cancellation path unless the task specifically concerns it.
- Surrounding EPUB context must never accidentally be synthesized as book text.
- Only the exact current Android/NeoReader synthesis request should be spoken unless a future architecture change is explicitly approved.
- Do not implement naive waiting or aggregation of future NeoReader TTS requests.
- Never hardcode, print, expose, or commit API credentials.
- Do not open, print, modify, or stage `backend/.env`.
- Do not commit or push unless explicitly asked.

## Development Workflow

Before a substantial implementation:

1. Inspect the relevant existing files.
2. Explain the proposed change and why.
3. Keep the change scoped to the requested milestone.
4. Identify important risks or architectural consequences.
5. Implement only after the approach is clear.

After meaningful Android changes, run:

```powershell
.\gradlew.bat assembleDebug
```

After meaningful backend Python changes, run appropriate syntax checks/tests before reporting success.

Do not claim NeoReader behavior is fixed or validated until it has been tested on the physical BOOX when physical-device validation is required.

Prefer evidence from ADB/logcat and backend logs over assumptions.

## Git and Safety Rules

Routine read-only or validation commands are acceptable, including:

```powershell
git status
git diff
git diff --cached
.\gradlew.bat assembleDebug
```

Do not perform any of the following unless explicitly requested:

```text
git commit
git push
git reset --hard
git clean -fd
git push --force
```

Do not make unrelated edits while completing a focused task.

## OpenAI API Work

When a task depends on current OpenAI API behavior, verify the current official OpenAI developer documentation rather than relying only on remembered API details.

Current project assumptions include:

- OpenAI speech model: `gpt-4o-mini-tts`
- OpenAI credentials remain on the backend only.
- Android/BOOX must never receive the OpenAI API key.
- The existing backend returns raw PCM for Android playback.

Do not change these assumptions silently.

## Physical Validation

The BOOX Go Color II is the target device.

Emulator or build success does not prove NeoReader compatibility.

For changes affecting Android TTS behavior, narration continuity, request handling, anchoring, audio delivery, or cancellation, provide the exact physical test steps needed after the build succeeds.

Do not install the APK or perform device-side actions unless explicitly requested or approved.

## Completion Report

At the end of a task, report:

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

Keep the report concise and distinguish clearly between:

- implemented behavior
- automated/build validation
- behavior still requiring physical BOOX verification
