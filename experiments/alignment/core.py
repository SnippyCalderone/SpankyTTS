"""Source-to-ASR reconciliation for the isolated Phase 2B.2B-1 proof.

All offsets use Python Unicode character indexes into the saved chapter text.
The source is never rewritten to match a recognizer's transcript.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


WORD_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
EXPLICIT_CONTRACTIONS = {"can't": ("can", "not"), "won't": ("will", "not"),
                         "shan't": ("shall", "not"), "cannot": ("can", "not"),
                         "o'clock": ("o", "clock")}
SUFFIXES = {"'re": "are", "'ve": "have", "'ll": "will", "'m": "am"}
INF = 10**12


@dataclass(frozen=True)
class SourceToken:
    index: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class AsrWord:
    index: int
    text: str
    start_ms: int
    end_ms: int
    probability: float | None = None


@dataclass(frozen=True)
class Edge:
    end_source: int
    end_asr: int
    kind: str
    cost: int


def source_tokens(text: str) -> list[SourceToken]:
    return [SourceToken(index, match.group(), match.start(), match.end())
            for index, match in enumerate(WORD_RE.finditer(text))]


def comparison_parts(text: str) -> tuple[str, ...]:
    """Return comparison units, without changing the stored source text.

    Only unambiguous, common contractions are expanded. Possessive/'s and
    'd are deliberately left alone because their spoken expansion varies.
    """
    normalized = unicodedata.normalize("NFKC", text).replace("’", "'").casefold()
    result: list[str] = []
    for match in WORD_RE.finditer(normalized):
        word = match.group()
        for piece in word.split("-"):
            if piece in EXPLICIT_CONTRACTIONS:
                result.extend(EXPLICIT_CONTRACTIONS[piece])
            elif piece.endswith("n't") and len(piece) > 3:
                result.extend((piece[:-3], "not"))
            elif any(piece.endswith(suffix) for suffix in SUFFIXES):
                suffix = next(s for s in SUFFIXES if piece.endswith(s))
                result.extend((piece[:-len(suffix)], SUFFIXES[suffix]))
            else:
                result.append(piece)
    return tuple(result)


def _edges(i: int, j: int, source: list[SourceToken], asr: list[AsrWord],
           source_parts: list[tuple[str, ...]], asr_parts: list[tuple[str, ...]]):
    m, n = len(source), len(asr)
    if i < m and j < n:
        if source_parts[i] and source_parts[i] == asr_parts[j]:
            asr_lexical = WORD_RE.findall(asr[j].text)
            exact = len(asr_lexical) == 1 and source[i].text == asr_lexical[0]
            yield Edge(i + 1, j + 1, "exact" if exact else "normalized", 0 if exact else 1)
        else:
            yield Edge(i + 1, j + 1, "substitution", 5)
        if (j + 1 < n and len(source_parts[i]) > 1 and
                source_parts[i] == asr_parts[j] + asr_parts[j + 1]):
            yield Edge(i + 1, j + 2, "normalized", 1)
        if (i + 1 < m and len(asr_parts[j]) > 1 and
                source_parts[i] + source_parts[i + 1] == asr_parts[j]):
            yield Edge(i + 2, j + 1, "normalized", 1)
    if i < m:
        yield Edge(i + 1, j, "omission", 3)
    if j < n:
        yield Edge(i, j + 1, "addition", 3)


def _ordered_path(source: list[SourceToken], asr: list[AsrWord]):
    """Find a minimum-cost ordered path and all source-token alternatives.

    Alternative assignments on equally good paths make repeated words
    uncertain. A deterministic tie break alone would conceal that ambiguity.
    """
    m, n = len(source), len(asr)
    source_parts = [comparison_parts(token.text) for token in source]
    asr_parts = [comparison_parts(word.text) for word in asr]
    forward = [[INF] * (n + 1) for _ in range(m + 1)]
    predecessor: list[list[tuple[int, int, Edge] | None]] = [
        [None] * (n + 1) for _ in range(m + 1)]
    forward[0][0] = 0
    for i in range(m + 1):
        for j in range(n + 1):
            if forward[i][j] == INF:
                continue
            for edge in _edges(i, j, source, asr, source_parts, asr_parts):
                candidate = forward[i][j] + edge.cost
                if candidate < forward[edge.end_source][edge.end_asr]:
                    forward[edge.end_source][edge.end_asr] = candidate
                    predecessor[edge.end_source][edge.end_asr] = (i, j, edge)

    backward = [[INF] * (n + 1) for _ in range(m + 1)]
    backward[m][n] = 0
    for i in range(m, -1, -1):
        for j in range(n, -1, -1):
            if i == m and j == n:
                continue
            backward[i][j] = min(
                (edge.cost + backward[edge.end_source][edge.end_asr]
                 for edge in _edges(i, j, source, asr, source_parts, asr_parts)),
                default=INF)

    alternatives: list[set[tuple[int, int, str]]] = [set() for _ in source]
    optimum = forward[m][n]
    for i in range(m + 1):
        for j in range(n + 1):
            if forward[i][j] == INF:
                continue
            for edge in _edges(i, j, source, asr, source_parts, asr_parts):
                if forward[i][j] + edge.cost + backward[edge.end_source][edge.end_asr] == optimum:
                    assignment = (j, edge.end_asr, edge.kind)
                    for source_index in range(i, edge.end_source):
                        alternatives[source_index].add(assignment)

    path: list[tuple[int, int, Edge]] = []
    i, j = m, n
    while i or j:
        previous = predecessor[i][j]
        if previous is None:
            raise ValueError("Could not reconstruct the source/ASR alignment")
        path.append(previous)
        i, j = previous[0], previous[1]
    path.reverse()
    ambiguous = {index for index, choices in enumerate(alternatives) if len(choices) > 1}
    return path, ambiguous, optimum


def _ambiguity_regions(tokens: list[SourceToken], ambiguous: set[int], chapter_start: int):
    regions = []
    for index in sorted(ambiguous):
        token = tokens[index]
        if regions and regions[-1]["source_token_end"] == index:
            regions[-1]["source_token_end"] = index + 1
            regions[-1]["block_end"] = token.end
            regions[-1]["chapter_end"] = chapter_start + token.end
        else:
            regions.append({"source_token_start": index, "source_token_end": index + 1,
                            "block_start": token.start, "block_end": token.end,
                            "chapter_start": chapter_start + token.start,
                            "chapter_end": chapter_start + token.end})
    return regions


def build_alignment(text: str, asr_words: list[AsrWord], chapter_start: int,
                    audio_duration_ms: int) -> dict:
    tokens = source_tokens(text)
    if not tokens or not asr_words:
        raise ValueError("Source and ASR must each contain spoken-word candidates")
    path, ambiguous, path_cost = _ordered_path(tokens, asr_words)
    bad_times: set[int] = set()
    timing_issues = []
    for index, word in enumerate(asr_words):
        if (word.start_ms < 0 or word.end_ms <= word.start_ms or
                word.end_ms > audio_duration_ms + 100 or
                (index and word.start_ms < asr_words[index - 1].start_ms)):
            bad_times.add(index)
            timing_issues.append({"asr_index": index, "start_ms": word.start_ms,
                                  "end_ms": word.end_ms})

    operations = []
    source_status = [None] * len(tokens)
    for i, j, edge in path:
        source_end_index, asr_end_index = edge.end_source, edge.end_asr
        source_start = tokens[i].start if i < len(tokens) else len(text)
        source_end = tokens[source_end_index - 1].end if source_end_index > i else source_start
        evidence_start = asr_words[j].start_ms if asr_end_index > j else None
        evidence_end = asr_words[asr_end_index - 1].end_ms if asr_end_index > j else None
        is_ambiguous = any(index in ambiguous for index in range(i, source_end_index))
        has_bad_time = any(index in bad_times for index in range(j, asr_end_index))
        reliable = edge.kind in {"exact", "normalized"} and not is_ambiguous and not has_bad_time
        status = "uncertain" if is_ambiguous or has_bad_time else edge.kind
        operation = {
            "status": status,
            "lexical_relation": edge.kind,
            "source_token_start": i, "source_token_end": source_end_index,
            "asr_word_start": j, "asr_word_end": asr_end_index,
            "block_start": source_start, "block_end": source_end,
            "chapter_start": chapter_start + source_start,
            "chapter_end": chapter_start + source_end,
            "source_text": text[source_start:source_end],
            "asr_text": " ".join(word.text.strip() for word in asr_words[j:asr_end_index]),
            "audio_start_ms": evidence_start if reliable else None,
            "audio_end_ms": evidence_end if reliable else None,
            "observed_asr_start_ms": evidence_start,
            "observed_asr_end_ms": evidence_end,
            "ambiguous": is_ambiguous,
            "timing_issue": has_bad_time,
        }
        operation_index = len(operations)
        operations.append(operation)
        for source_index in range(i, source_end_index):
            source_status[source_index] = (status, operation_index)

    token_rows = [{"index": token.index, "text": token.text,
                   "block_start": token.start, "block_end": token.end,
                   "chapter_start": chapter_start + token.start,
                   "chapter_end": chapter_start + token.end,
                   "status": source_status[token.index][0],
                   "operation_index": source_status[token.index][1]}
                  for token in tokens]
    summary = {
        "source_whitespace_words": len(text.split()),
        "source_tokens": len(tokens), "asr_words": len(asr_words),
        "exact_matches": sum(op["source_token_end"] - op["source_token_start"]
                             for op in operations if op["status"] == "exact"),
        "normalized_matches": sum(op["source_token_end"] - op["source_token_start"]
                                  for op in operations if op["status"] == "normalized"),
        "substitutions": sum(op["source_token_end"] - op["source_token_start"]
                             for op in operations if op["lexical_relation"] == "substitution"),
        "possible_omissions": sum(op["source_token_end"] - op["source_token_start"]
                                  for op in operations if op["lexical_relation"] == "omission"),
        "asr_additions": sum(op["asr_word_end"] - op["asr_word_start"]
                             for op in operations if op["lexical_relation"] == "addition"),
        "ambiguous_source_tokens": len(ambiguous),
        "ambiguous_regions": _ambiguity_regions(tokens, ambiguous, chapter_start),
        "timing_issues": timing_issues,
        "alignment_path_cost": path_cost,
    }
    first = next(op for op in operations if op["source_token_start"] == 0 and
                 op["source_token_end"] > 0)
    last = next(op for op in reversed(operations) if op["source_token_end"] == len(tokens)
                and op["source_token_start"] < len(tokens))
    summary["first_source_word"] = {"text": tokens[0].text,
                                    "chapter_start": chapter_start + tokens[0].start,
                                    "audio_start_ms": first["audio_start_ms"],
                                    "status": first["status"]}
    summary["last_source_word"] = {"text": tokens[-1].text,
                                   "chapter_end": chapter_start + tokens[-1].end,
                                   "audio_end_ms": last["audio_end_ms"],
                                   "status": last["status"]}
    summary["beginning_supported_by_asr"] = first["audio_start_ms"] is not None and first["asr_word_start"] == 0
    summary["ending_supported_by_asr"] = last["audio_end_ms"] is not None and last["asr_word_end"] == len(asr_words)
    summary["block_status"] = "ALIGNED_BUT_UNCERTAIN"
    summary["cache_eligible"] = False
    summary["verification_reason"] = (
        "ASR and ordered matching are automated evidence. Full audio/source review and "
        "resolution of every disagreement are required before VERIFIED or cached use.")
    return {"schema_version": 1, "coordinate_system": "saved chapter_source.txt Unicode character offsets",
            "chapter_source_start": chapter_start,
            "chapter_source_end": chapter_start + len(text),
            "audio_duration_ms": audio_duration_ms,
            "source_text": text, "source_tokens": token_rows,
            "operations": operations, "summary": summary}


def lookup(artifact: dict, start: int, end: int, coordinate: str = "chapter") -> dict:
    """Resolve a complete-word source range, never interpolating missing words."""
    if coordinate not in {"chapter", "block"}:
        raise ValueError("coordinate must be 'chapter' or 'block'")
    offset = artifact["chapter_source_start"] if coordinate == "chapter" else 0
    local_start, local_end = start - offset, end - offset
    source_length = len(artifact["source_text"])

    def reject(reason: str, status: str = "REJECTED") -> dict:
        return {"requested_start": start, "requested_end": end,
                "coordinate": coordinate, "status": status,
                "cache_eligible": False,
                "audio_start_ms": None, "audio_end_ms": None, "reason": reason}

    if not 0 <= local_start < local_end <= source_length:
        return reject("Range is empty or outside this source block")
    selected = [token for token in artifact["source_tokens"]
                if token["block_start"] < local_end and token["block_end"] > local_start]
    if not selected:
        return reject("Range contains punctuation or whitespace but no source word", "UNCERTAIN")
    if local_start > selected[0]["block_start"] or local_end < selected[-1]["block_end"]:
        return reject("Range splits a source word", "UNCERTAIN")

    first_index, last_index = selected[0]["index"], selected[-1]["index"]
    relevant = []
    for op in artifact["operations"]:
        if op["source_token_start"] < last_index + 1 and op["source_token_end"] > first_index:
            relevant.append(op)
        elif op["lexical_relation"] == "addition" and local_start <= op["block_start"] <= local_end:
            return reject("Extra ASR word occurs within the requested source range", "UNCERTAIN")
    if any(op["source_token_start"] < first_index or op["source_token_end"] > last_index + 1
           for op in relevant):
        return reject("Range divides a multiword alignment group", "UNCERTAIN")
    bad = [op for op in relevant if op["audio_start_ms"] is None]
    if bad:
        kinds = ", ".join(sorted({op["status"] for op in bad}))
        return reject(f"Range contains unmatched or uncertain source words: {kinds}", "UNCERTAIN")
    times = [op["audio_start_ms"] for op in relevant]
    ends = [op["audio_end_ms"] for op in relevant]
    if any(right < left for left, right in zip(times, times[1:])) or ends[-1] <= times[0]:
        return reject("Mapped word times are not monotonic", "UNCERTAIN")
    status = ("VERIFIED" if artifact["summary"]["block_status"] == "VERIFIED"
              else "ALIGNED_BUT_UNCERTAIN")
    return {"requested_start": start, "requested_end": end, "coordinate": coordinate,
            "status": status, "match_quality": "normalized" if any(
                op["status"] == "normalized" for op in relevant) else "exact",
            "cache_eligible": artifact["summary"].get("cache_eligible", False) and status == "VERIFIED",
            "audio_start_ms": times[0], "audio_end_ms": ends[-1],
            "reason": ("All selected source words have ordered timestamp matches; "
                       "block verification is still pending." if status != "VERIFIED" else
                       "Verified source/audio range")}
