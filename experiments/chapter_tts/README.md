# Chapter TTS listening experiment

This developer-only utility uses a native file picker and a terminal chapter menu to generate one EPUB chapter as sequential OpenAI MP3 parts. It does not use the Android app or the production `/tts` endpoint.

## Feasibility result and limit

The long-form feasibility milestone is validated. Two Chapter Five listening runs found materially better continuity, pacing, dialogue transitions, and audiobook quality than short independent NeoReader requests. The second run resolved the observed middle-of-chapter omissions. The remaining known issue is that generative TTS can omit text at the absolute end of the final block even when the exact source and planned block files contain it. In isolated tests, the final sentence was spoken when genuine next-chapter text followed it, and when fidelity instructions were added to the short final paragraph. The later full-chapter run still omitted that sentence despite the fidelity instructions.

This utility does not perform transcription, source/audio alignment, cached slicing, or NeoReader playback. Its MP3 output must not be used as if it already maps to individual NeoReader requests. The live per-request TTS path remains the working fallback while alignment and verified slicing are developed.

From the repository root in PowerShell:

```powershell
backend\.venv\Scripts\python.exe -m pip install -r experiments\chapter_tts\requirements.txt
backend\.venv\Scripts\python.exe experiments\chapter_tts\chapter_tts.py
```

Edit `narration_profile.json` to change the model, voice, speed, or narration directions. The default profile now includes the Test C text and ending fidelity language for every chapter request, along with scene dynamics, dialogue tags, and interruption handling. It keeps cedar at speed 1.0 and a consistent audiobook narrator identity. The assembled instructions must fit within 4,096 characters. The script uses `OPENAI_API_KEY` from the process environment or the existing ignored `backend/.env`; it never displays the key. No key is needed to list chapters, inspect the block plan, or answer `N`.

After selecting an EPUB and a chapter, review the planned parts and answer `Y` to make paid Speech API requests. Requests run one at a time with automatic retries disabled. Output is under the Git-ignored `output/<book>/<chapter>/<timestamp>/` directory. It contains `chapter_source.txt`, `part_001.txt` and matching MP3 files, `run_summary.json`, and, when FFmpeg succeeds, `chapter_complete.mp3`. The text files hold the exact strings sent to the API. Treat these files as local copies of the book.

The script targets 3,550 characters per block, below the documented 4,096-character Speech API input maximum. It favors paragraph, then sentence, then word boundaries. A non-final block with a terminal paragraph of at most 120 characters is cut at the preceding safe paragraph boundary so that paragraph starts the next block. The final chapter block is unchanged. EPUB navigation entries determine chapter names and spans when available; document headings and spine sections are fallbacks. EPUBs vary, so review the extracted text and block plan before agreeing to generation.

`ffprobe` measures MP3 duration and `ffmpeg` concatenates with stream copy. Both commands must be available on `PATH` for the full report and combined file. Stream copy avoids re-encoding, but independently encoded MP3s may have a small seam at a boundary. An FFmpeg failure preserves the generated parts.

For a repeatable local test without the file picker, use `--epub PATH` and answer `N` at the prompt. This does not call OpenAI or create an output directory.

## Final paragraph diagnostic

Run `backend\.venv\Scripts\python.exe experiments\chapter_tts\diagnose_final.py` to compare only the selected chapter's genuine final paragraph (Test A) with that same paragraph followed by up to 300 characters from the next readable EPUB section (Test B). Use `--epub PATH` to skip the file picker. The terminal shows both character counts, the exact extracted-text offsets, the full appended text, and a two-request estimate before asking `Y/N`. Answering `N` makes no API request and writes no diagnostic output.

After `Y`, the script uses the current `narration_profile.json` settings for both requests. It writes exact inputs, labeled MP3s, and `diagnostic_summary.json` under the ignored `output/diagnostics/` directory. It reports each duration with `ffprobe`, generation time, and filenames. The normal chapter generator and its block planner are unchanged by this diagnostic.

The historical Test C mode is available with `--test-c-fidelity`. With the current default profile, its fidelity wording is already present, so the mode does not append a duplicate copy. It still previews the exact final paragraph and instructions before asking for one paid request. A new Test C run with this revised profile would not reproduce the original baseline-versus-addendum comparison.

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s experiments\chapter_tts\tests -v
```
