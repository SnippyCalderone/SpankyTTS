# Spanky TTS — Codex Repository Instructions

## Project Orientation

This is an existing project. Do not treat it as a greenfield Android application.

Use the project documentation selectively:

- Read `STATUS.md` to determine the current milestone, verified progress, and next action.
- Read `ROADMAP.md` for the planned sequence and milestone dependencies before substantial work.
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
- Phase 2B.2A context-aware delivery is complete and physically checked on the BOOX.
- Larger-generation-unit feasibility is validated in a standalone experiment.
- **M0D.1 — Character Research & Voice Profile Foundation** is the immediate development focus, followed by M0D.2 custom voice creation, M0D.3 audition/refinement, and M0D.4 isolated character-aware chapter narration. These stages are planned, not implemented.
- Gemini 3.8 Flash TTS is the selected target for custom character voices and planned audiobook narration. The existing Gemini Narrator Lab is an isolated experiment; it does not supply production playback.
- **Phase 2B.2B — Alignment and Cached Playback** is deferred, not discarded. A standalone one-block candidate and review clips exist, but the saved result is `ALIGNED_BUT_UNCERTAIN`; human review, verified slicing, and playback integration remain pending. Production character-voice integration with NeoReader depends on a proven exact-request cached playback path.
- Master Voice Library M0A–M0C is complete as a local SQLite catalog with 16 synchronized Gemini voices and one preferred character assignment. It is not connected to narration generation or Android/NeoReader playback.

Keep implementation scoped to the requested milestone in `ROADMAP.md`. M0D.1 supports manual profiles and reusable, spoiler-aware research; it does not create voices or change playback. Do not pull cache, pre-generation, character evolution, or Android integration into M0D.1–M0D.3.

For M0D work, require explicit user authorization before each paid research
operation and before Gemini voice creation or regeneration. Ordinary viewing or
editing of saved dossiers, prompt compilation, and offline tests must not make
API calls. Preserve locally saved research results and citations for reuse.
M0D.4 may start with short, manually attributed dialogue and controlled chapter
excerpts; automated attribution, scene-level voice switching, and full-book
character mapping are deferred.

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

- Existing live Android/FastAPI speech model: OpenAI `gpt-4o-mini-tts`, physically verified on the BOOX.
- Planned OpenAI work: character research, dossier compilation, voice-description prompts, and optional later narration analysis/orchestration.
- Selected future voice/narration target: Gemini 3.8 Flash TTS; no Gemini-to-NeoReader integration exists.
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
