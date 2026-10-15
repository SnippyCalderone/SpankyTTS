# Spanky TTS — Development Roadmap

This is the planned sequence. `STATUS.md` records verified progress; `PROJECT_CONTEXT.md` records architectural constraints. A planned milestone below is not an implementation claim.

## Current position — 2026-10-15

**Track A: Phase 2B.2B-1, single-block source/audio alignment proof, is next.** Use one existing approximately 3,000-character generated narration block. Find reliable audio timestamps for known EPUB source offsets and check whether the beginning and end were actually spoken. No aligned cache, audio slicing, or cached NeoReader playback works yet.

**Track B: Narrator Lab may run in parallel.** It is an isolated quality experiment and does not block Track A.

## Proven foundation

| Milestone | Status | Evidence and boundary |
| --- | --- | --- |
| Phase 1 — Android TTS and NeoReader integration | Complete | Physical BOOX playback and cancellation; NeoReader was observed splitting book text upstream. |
| Phase 2A — EPUB anchoring | Complete | Spine-aware index, rolling matcher, conservative ambiguity handling, and re-anchor recovery. |
| Phase 2B.1 — live OpenAI PCM path | Complete | Physical BOOX NeoReader playback, backend transport, callbacks, and cancellation. |
| Phase 2B.2A — context-aware per-request delivery | Complete | Physical comparison found modest gains and no spoken surrounding EPUB text; request-boundary resets remain. |
| Larger-generation-unit feasibility | Validated | Standalone chapter experiment produced more coherent audio. It did not implement alignment or NeoReader playback; absolute final-sentence omission remains unresolved. |

## Dependency path

```text
Proven EPUB anchoring + live PCM fallback + larger-block feasibility
                         ↓
2B.2B-1 align one block → 2B.2B-2 verify exact slices
                         ↓
             2B.2B-3 simulate NeoReader requests
                         ↓
             2B.2B-4 integrate cached playback
                         ↓
             2B.2B-5 pre-generate and look ahead
                         ↓
       production character voices / scene audio
                         ↓
                 polish and release work

Narrator Lab experiments run alongside the Track A sequence and can inform
master-generation quality without changing its delivery contract.
```

## Track A — core engineering, primary and required

The design generates natural larger narration units ahead of NeoReader requests. It does **not** predict NeoReader's request boundaries. Once a request arrives, the Phase 2A matcher identifies its exact EPUB source span; a verified alignment map finds the corresponding audio span. Only that span is eligible for callback delivery. If the anchor or slice is unverified, use the existing live per-request OpenAI TTS path.

### 2B.2B-1 — Single-block alignment proof — immediate task

- Take one already generated approximately 3,000-character narration block and its exact EPUB source text/offsets.
- Evaluate forced alignment, transcription with word timestamps, model/provider timing metadata if available, and a hybrid approach before choosing one.
- Map known EPUB character/source offsets to audio timestamps and show deterministic source-text to audio-time lookup.
- Detect omitted or altered speech, especially at the beginning and absolute end; text present in the block plan alone is insufficient.
- Record confidence/verification rules that can reject uncertain spans. Keep this experiment separate from Android playback.

**Exit evidence:** repeatable lookup results for the selected block and an explicit account of spoken completeness and uncertain boundaries.

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

## Track B — Narrator Lab, parallel and experimental

Recommended location: `experiments/narrator_lab/`. Keep artifacts and comparisons separate from production Android playback. Use the same short source excerpt for A/B comparisons and preserve strict text fidelity.

1. Establish repeatable voice and narration-instruction comparisons.
2. Refine pacing, emotional range, scene dynamics, and dialogue delivery.
3. Test speech verbs, dialogue tags, adverbs, interruptions, and em-dash delivery. A cue may follow its quoted line; it should guide that dialogue while the attribution remains natural narration.
4. Record listening results and fidelity issues to inform later master generation.

Track B may proceed between Track A milestones. Its experiments do not block, redefine, or replace alignment and cached playback.

## Later work that depends on aligned cached playback

- **Character voices:** experiment early if useful, but wait for proven cached aligned delivery before production integration.
- **Scene-aware generation and sound effects:** keep generated master audio mapped to EPUB source spans and delivered as exact NeoReader request slices.
- **Product polish and release:** voice presets and preview, settings and cache management, network/error UI, configurable and safer backend deployment, performance and reliability work, and physical-device regression checks.

Narrator, character, and scene generation may make the master audio more complex. NeoReader still sees the same exact-request PCM delivery contract and remains unaware of that generation strategy.

## Alternating development cadence

The intended order interleaves engineering proofs with enjoyable quality work:

1. Alignment design.
2. Single-block alignment experiment.
3. Narrator-quality experiment.
4. Cached slicing experiment.
5. Narrator/dialogue-quality refinement.
6. NeoReader request simulation.
7. Android cached playback integration.
8. Further narrator/character experimentation, without production character integration yet.
9. Pre-generation/look-ahead queue.

This cadence prevents long stretches of only alignment plumbing and avoids polishing voices before NeoReader can receive their audio correctly. Track A's exit evidence, rather than the cadence alone, gates production integration.
