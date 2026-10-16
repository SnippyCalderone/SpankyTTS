# Phase 2B.2B-1: one-block source/audio alignment proof

This PC-only experiment maps words in one saved EPUB chapter block to timed words
recognized from its existing narration MP3. It does not change Android, the
backend, or the Chapter Five fixture. It makes no OpenAI API call and does not
create playback slices.

## Fixed fixture

`fixture.json` identifies the Chapter Five `20261014_060811_408632` run's
`part_002.txt` and `part_002.mp3`, with repository-relative paths, SHA-256 hashes,
chapter-source character range `[3177, 6385)`, counts, and audio duration. The
script refuses to run if a hash, source span, run summary, or duration differs.
Offsets refer to Unicode characters in that run's saved `chapter_source.txt`.
They are **not** Android's normalized EPUB index offsets.

## Local setup and run

From the repository root in PowerShell:

```powershell
python -m venv experiments\alignment\.venv
experiments\alignment\.venv\Scripts\python.exe -m pip install -r experiments\alignment\requirements.txt
experiments\alignment\.venv\Scripts\python.exe experiments\alignment\run.py download-model
experiments\alignment\.venv\Scripts\python.exe experiments\alignment\run.py run
experiments\alignment\.venv\Scripts\python.exe -m unittest discover -s experiments\alignment\tests -v
```

The direct pins are `faster-whisper==1.2.1` and `av==18.1.0`; the complete
resolved set for this Windows/Python 3.13.3 run is in `requirements-lock.txt`.
To reproduce that exact environment, install the lock file in place of
`requirements.txt`.
PyAV 19 removed an argument that faster-whisper 1.2.1 still passes to `av.open`.
The `download-model` step obtains `Systran/faster-whisper-small.en` into the
ignored `experiments/alignment/.models/` cache. Its revision and weight SHA-256
are pinned in `run.py`. `run` uses that local snapshot
without network access, on CPU with int8, English selected, word timestamps on,
and VAD off. It does not pass the source text to ASR as a prompt. The virtual
environment, model cache, and output files are ignored by Git.

For a deterministic remap of the saved transcription without running ASR again:

```powershell
experiments\alignment\.venv\Scripts\python.exe experiments\alignment\run.py reconcile
```

To query a half-open chapter-source range, for example:

```powershell
experiments\alignment\.venv\Scripts\python.exe experiments\alignment\run.py lookup 5524 5542
```

Pass `--coordinate block` to use offsets relative to `part_002.txt` instead.
The query accepts whole source words with optional surrounding punctuation or
whitespace. It rejects splits inside a word, punctuation-only spans, unmatched
words, ambiguous groups, and ASR additions within the requested range.

To prepare the human listening pass from the **saved** ASR and alignment (without
retranscribing or changing the fixture):

```powershell
experiments\alignment\.venv\Scripts\python.exe experiments\alignment\make_review.py
```

This writes `review/review.md`, `review/review_manifest.json`, and numbered WAV
clips under the ignored output directory. The report covers every non-clean
operation, combines the adjacent blue-gray addition and ambiguous token into one
passage, and adds dedicated beginning/end checks. It records exact source
offsets, raw ASR time evidence, surrounding text, and expected source text for
each clip. Clips include about two seconds of context around a discrepancy;
the block-edge clips use six seconds. These windows are only listening aids,
never production slice boundaries. Generating them does not verify the block.

## Method and artifacts

`run.py` saves these files under the ignored
`experiments/alignment/output/<fixture-id>/` directory:

- `raw_asr.json`: unmodified recognizer text, word timestamps, probabilities,
  segments, and measured runtime; no EPUB transcript is supplied to the model.
- `alignment.json`: unchanged source text, every source token's block and chapter
  offsets, ordered source/ASR operations, valid mapped times, and summary.
- `model_identity.json`: model repository, snapshot revision, weight/config/tokenizer
  hashes, package versions, and ASR settings.
- `requirements_resolved.txt`: every version installed in the isolated environment.

Comparison normalization handles case, curly apostrophes, punctuation, hyphens,
and a small set of unambiguous contractions. It never edits the saved source.
Ordered dynamic programming chooses a minimum-cost path and checks all equally
optimal assignments. Repeated-word alternatives are marked uncertain. Missing
source words, extra ASR words, substitutions, ambiguous assignments, and invalid
or zero-duration timestamps never receive invented source-to-audio times.

`exact` means the lexical spelling and case match; punctuation is not treated
as a spoken word. `normalized` means a comparison-only form matched, including
case or an explicit contraction expansion. Neither label proves that the audio
spoke the original text exactly. Each lookup returns match quality and the
block's verification status separately.

## Verification boundary

The automated result remains `ALIGNED_BUT_UNCERTAIN`. `VERIFIED` requires a
full listen against the authoritative source, explicit resolution of every
disagreement and suspect timestamp, and boundary review. A human-confirmed
missing word would make the block `INCOMPLETE`; a damaged fixture or unusable
alignment would be `REJECTED`. No cached playback is eligible from this result.

ASR may miss, add, or respell words; forced alignment can also assign time to
unspoken supplied words. Word stamps are approximate, and punctuation has no
independent audio interval. Later work must translate this experiment's chapter
offsets to Android's normalized EPUB index and test actual cut boundaries.
