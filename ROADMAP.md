# Spanky TTS — Development Roadmap

This is the planned sequence. `STATUS.md` records verified progress; `PROJECT_CONTEXT.md` records architectural constraints. A planned milestone below is not an implementation claim.

## Current position — 2026-10-24

**Immediate priority: Master Voice Library M0D.1, Character Research & Voice Profile Foundation.** This is planned, not implemented. M0D.1–M0D.3 establish reusable character research, voice design, and audition before character-aware chapter narration in M0D.4. Gemini 3.8 Flash TTS is the selected target for custom character voices and planned audiobook generation; it has not replaced the verified OpenAI live playback path.

**Deferred engineering: Phase 2B.2B-1 alignment proof.** A standalone Whisper ASR/source-token experiment produced a candidate map and listening-review clips for an existing OpenAI block. Its saved status is `ALIGNED_BUT_UNCERTAIN`; the full listen, discrepancy resolution, beginning/end checks, and verified lookup remain. No aligned cache, audio slicing, or cached NeoReader playback works yet. Preserve this work for later exact-request playback integration.

**Completed catalog: Master Voice Library M0A–M0C.** Sixteen Gemini voices are synchronized and Gabriel de León has a preferred slot 1 assignment. The existing Narrator Lab is isolated and experimental; neither its output nor library assignments reach NeoReader.

## Proven foundation

| Milestone | Status | Evidence and boundary |
| --- | --- | --- |
| Phase 1 — Android TTS and NeoReader integration | Complete | Physical BOOX playback and cancellation; NeoReader was observed splitting book text upstream. |
| Phase 2A — EPUB anchoring | Complete | Spine-aware index, rolling matcher, conservative ambiguity handling, and re-anchor recovery. |
| Phase 2B.1 — live OpenAI PCM path | Complete | Physical BOOX NeoReader playback, backend transport, callbacks, and cancellation. |
| Phase 2B.2A — context-aware per-request delivery | Complete | Physical comparison found modest gains and no spoken surrounding EPUB text; request-boundary resets remain. |
| Larger-generation-unit feasibility | Validated | Standalone chapter experiment produced more coherent audio. It did not implement alignment or NeoReader playback; absolute final-sentence omission remains unresolved. |
| Master Voice Library M0A–M0B | Complete | Versioned SQLite catalog, stable project-scoped voice IDs, read-only Google sync; 16 voices imported in one complete page with zero duplicates. |
| Master Voice Library M0C | Complete | Schema v2, scoped characters, local annotations/tags, assignments, preference/history, warnings; backed-up migration preserved all 16 voice rows. |
| First character-to-voice assignment | Complete locally | Empire of the Vampire / Gabriel de León → Gemini “Gabriel de León 2”, slot 1, preferred; no narration or Android integration. |
| 2B.2B-1 automated alignment candidate | Deferred after candidate | One-block source/ASR map and review clips exist; saved result `ALIGNED_BUT_UNCERTAIN`, not cache eligible. |

## Development sequence

```text
M0A–M0C catalog (complete)
  → M0D.1 research, editable profiles, and three voice-design prompts
  → M0D.2 approved Gemini custom voice creation and catalog registration
  → M0D.3 audition, refine, and select preferred voices
  → M0D.4 isolated Gemini character-aware chapter narration experiment

Later: verify alignment → slice exact requests → simulate NeoReader requests
       → integrate cached playback → pre-generate and look ahead
       → consider character-aware NeoReader playback
```

## M0D — Character research, voice design, and narration experiments

M0D is the immediate development focus. Its first three stages are local research and voice-library work; they do not depend on source/audio alignment or change Android playback. OpenAI models are planned for online character research, dossier compilation, voice-description prompt engineering, and later narration analysis or orchestration where useful. Gemini 3.8 Flash TTS is the selected target for persistent character voice creation and planned audiobook narration. Provider use, credentials, and costs require explicit controls when implemented. The existing OpenAI `gpt-4o-mini-tts` backend remains the physically verified NeoReader path.

### M0D.1 — Character Research & Voice Profile Foundation — next

- Research a selected character with OpenAI and cited online sources, or enter a profile manually without online research. Optionally analyze user-provided EPUB content within an explicit spoiler cutoff.
- Store an editable, spoiler-aware dossier with source provenance. Separate confirmed facts, reasonable inferences, and creative vocal choices; surface conflicting evidence for review.
- Require explicit user authorization for each paid research operation. Save research results and citations locally for reuse; viewing or editing a dossier, compiling prompts, and running offline tests make no API calls.
- Represent stable vocal characteristics in provider-neutral form, then compile a Gemini-specific voice-design description.
- Produce three distinct initial design **prompts** for the same character. Inspect existing approved library voices and provider IDs first; suitable voices should be reused rather than automatically regenerated.
- Keep profile and candidate history extensible for multiple variants per character without building a character-evolution engine.

**Exit evidence:** offline and mocked research tests show cutoff enforcement, traceable citations, manual entry, editable revisions, three distinct prompts, and no provider voice creation or changed preferred assignment.

### M0D.2 — Gemini Custom Voice Creation

- Create persistent custom Gemini voices only from approved prompts with explicit user authorization for each creation or regeneration operation.
- Capture provider voice IDs, model, prompt revision, usage, preview metadata, and lineage; register voices in the Master Voice Library without losing existing records.
- Check existing voices and prior creation records to avoid duplicate generation. Preserve historical candidates.

**Depends on:** M0D.1. **Exit evidence:** mocked provider tests, explicit paid-call boundary, and stable catalog registration; live generation only after separate approval.

### M0D.3 — Voice Audition & Refinement

- Audition up to three active candidates using the same standardized dialogue and comparable synthesis settings.
- Edit design prompts and, with explicit user authorization, generate a new voice revision when needed; retain prior voice IDs, audio metadata, ratings, and listening notes.
- Select the preferred assignment explicitly through existing library preference management.

**Depends on:** M0D.2. **Exit evidence:** repeatable comparisons, recorded evaluations and revisions, and no silent preference switch.

### M0D.4 — Character-Aware Chapter Narration

- Begin with short, manually attributed dialogue and controlled chapter excerpts using approved character voices, independently of Android and NeoReader. Automated dialogue attribution is not a prerequisite.
- Preserve exact EPUB source text and evaluate the supplied dialogue attribution, speaker identity, continuity, and spoken-word fidelity.
- Treat generated audio as experimental until completeness and later source/audio alignment are verified.

Automated dialogue attribution, scene-level voice switching, and full-book
character mapping remain deferred beyond M0D.4's initial controlled experiments.

**Depends on:** M0D.3. **Exit evidence:** saved, reviewable chapter experiments with exact source identity and listening/fidelity findings; no production playback claim.

## Deferred engineering — Phase 2B.2B alignment and cached playback

The following research and implementation path remains valid but is not the current M0D.1–M0D.3 work. The saved alignment result is still `ALIGNED_BUT_UNCERTAIN`. Character-aware NeoReader playback depends on verified exact-request slices, but local voice design and isolated chapter experiments can proceed first.

The design generates natural larger narration units ahead of NeoReader requests. It does **not** predict NeoReader's request boundaries. Once a request arrives, the Phase 2A matcher identifies its exact EPUB source span; a verified alignment map finds the corresponding audio span. Only that span is eligible for callback delivery. If the anchor or slice is unverified, use the existing live per-request OpenAI TTS path.

### 2B.2B-1 — Single-block alignment proof — human verification pending

- Take one already generated approximately 3,000-character narration block and its exact EPUB source text/offsets.
- Review the existing Whisper ASR/source-token candidate map against the audio; investigate other alignment methods if discrepancies cannot be resolved reliably.
- Map known EPUB character/source offsets to audio timestamps and show deterministic source-text to audio-time lookup.
- Resolve every uncertain/missing/extra word and check the beginning and absolute end by listening; text present in the block plan alone is insufficient.
- Record confidence/verification rules that can reject uncertain spans. Keep this experiment separate from Android playback.

**Exit evidence:** repeatable lookup results for the selected block and an explicit account of spoken completeness and uncertain boundaries.

The saved automated result is `ALIGNED_BUT_UNCERTAIN`, so this exit evidence is not yet met. See [the alignment experiment](experiments/alignment/README.md).

### 2B.2B-2 — Verified audio slicing

- Ask for arbitrary source spans within a verified aligned block; retrieve and cut corresponding cached PCM.
- Listen and inspect boundaries for clipped first/last words and adjacent meaningful words leaking into the slice.
- Investigate small padding or crossfade only if it improves boundaries without speaking words outside the requested span.
- Reject unverified slices rather than guessing.

**Depends on:** 2B.2B-1. **Exit evidence:** exact-span slices across varied positions, including block edges.

### 2B.2B-3 — NeoReader request simulation

- Replay previously observed NeoReader request patterns through `TextAnchorMatcher → source offsets → alignment map → cached audio slice`.
- Concatenate and listen to the returned slices; compare continuity with the original larger generation.
- Test ambiguous/repeated anchors, gaps, and missing audio as fallback cases.

**Depends on:** 2B.2B-2. **Exit evidence:** a request-by-request mapping and playback review without extra or missing book words.

### 2B.2B-4 — Android cached playback integration

- For each NeoReader request, use a cached slice only when the Phase 2A anchor and alignment are reliable.
- Otherwise call the proven live per-request backend path. Keep callback size limits, cancellation, exact-request speech, and backend-only API credentials.
- Build and test on the physical BOOX before claiming NeoReader playback or highlighting synchronization.

**Depends on:** 2B.2B-3. **Exit evidence:** physical BOOX logs, listening, and visual observation show correct cached hits, live misses, request boundaries, highlighting, and cancellation.

### 2B.2B-5 — Pre-generation and look-ahead queue

- Generate several natural blocks ahead of the current reading position, align them as they finish, and cache only verified results.
- Maintain a small look-ahead queue; do not require whole-book generation before reading starts.
- Handle cache misses and failures through the live path. Use cache identity that accounts for source text, model, voice, instructions, and relevant settings.
- Address chapter-boundary generation and the known terminal-position omission as later work within this stage, with completeness checks before cache eligibility.

**Depends on:** 2B.2B-4. **Exit evidence:** continuous physical reading across hits and misses, bounded queue behavior, and verified boundary handling.

## Existing Narrator Lab — isolated experiment

The current isolated [Gemini Narrator Lab](experiments/gemini_tts/README.md) lives in `experiments/gemini_tts/`. Keep artifacts and comparisons separate from production Android playback. Use the same short source excerpt for A/B comparisons and preserve strict text fidelity.

1. Establish repeatable voice and narration-instruction comparisons.
2. Refine pacing, emotional range, scene dynamics, and dialogue delivery.
3. Test speech verbs, dialogue tags, adverbs, interruptions, and em-dash delivery. A cue may follow its quoted line; it should guide that dialogue while the attribution remains natural narration.
4. Record listening results and fidelity issues to inform later master generation.

The lab is available for controlled comparisons and may inform M0D.4. It does not yet use preferred library assignments, create character voices, or change Android playback.

## Master Voice Library — completed foundation for M0D

**Completed:** M0A SQLite foundation and stable provider-qualified voice identities; M0B registered Gemini project and successful read-only sync of 16 voices; M0C schema v2, scoped characters, local metadata, tags, up to three active assignments, preference/history, and availability/expiration diagnostics. The backed-up migration preserved all 16 voices. The Empire of the Vampire series scope and Gabriel de León are registered, and Gemini “Gabriel de León 2” is Gabriel's preferred slot 1 voice.

**Next local voice work:** use Ashdrinker as an illustrative M0D.1 character with an end-of-first-book spoiler cutoff, refine existing voices where suitable, and register further characters. M0D.2–M0D.3 add explicit creation and audition; paid generation requires its own approval.

**Pending integration:** connect the library to narration generation with explicit voice identity and text fidelity, then to SpankyTTS only after the source-aligned cache and exact-request playback path have been proven. A local assignment does not change today's Android/NeoReader speech.

## Future evolution and playback capabilities

- Automated character aging and evolution-state extraction; permanent and temporary vocal changes.
- Flashback and nonlinear timeline analysis; scene-level voice assignment; exact EPUB text-range to voice-state mapping.
- **Production character voices:** wait for proven cached aligned delivery before NeoReader integration.
- **Scene-aware generation and sound effects:** keep generated master audio mapped to EPUB source spans and delivered as exact NeoReader request slices.
- **Product polish and release:** voice presets and preview, settings and cache management, network/error UI, configurable and safer backend deployment, performance and reliability work, and physical-device regression checks.

Narrator, character, and scene generation may make the master audio more complex. NeoReader still sees the same exact-request PCM delivery contract and remains unaware of that generation strategy.

The earlier alignment-first cadence has been superseded by M0D.1–M0D.4 as the next development sequence. The detailed Phase 2B.2B stages above preserve the engineering evidence and gates for later NeoReader integration.
