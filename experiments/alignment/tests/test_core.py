"""Small audio-independent checks for reconciliation and conservative lookup."""

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import AsrWord, build_alignment, lookup  # noqa: E402


def aligned(source: str, *words: str) -> dict:
    asr = [AsrWord(index, word, index * 500, index * 500 + 400, 0.9)
           for index, word in enumerate(words)]
    return build_alignment(source, asr, 1000, len(words) * 500 + 100)


class ReconciliationTests(unittest.TestCase):
    def test_exact_match_and_chapter_offset_lookup(self):
        result = aligned("Hello world", "Hello", "world")
        self.assertEqual(2, result["summary"]["exact_matches"])
        self.assertTrue(result["summary"]["beginning_supported_by_asr"])
        self.assertTrue(result["summary"]["ending_supported_by_asr"])
        match = lookup(result, 1000, 1011)
        self.assertEqual((0, 900), (match["audio_start_ms"], match["audio_end_ms"]))
        self.assertEqual("ALIGNED_BUT_UNCERTAIN", match["status"])

    def test_punctuation_case_and_quotes_do_not_change_source(self):
        source = "“Hello,” world!"
        result = aligned(source, "hello", "world.")
        self.assertEqual(source, result["source_text"])
        self.assertEqual(1, result["summary"]["normalized_matches"])
        self.assertEqual(1, result["summary"]["exact_matches"])
        self.assertEqual("Hello", result["source_tokens"][0]["text"])
        self.assertEqual(0, lookup(result, 1000, 1007)["audio_start_ms"])

    def test_contraction_expansion_is_a_group(self):
        result = aligned("don't go", "do", "not", "go")
        self.assertEqual(1, result["summary"]["normalized_matches"])
        self.assertEqual((0, 900),
                         (lookup(result, 1000, 1005)["audio_start_ms"],
                          lookup(result, 1000, 1005)["audio_end_ms"]))
        reverse = aligned("do not", "don't")
        self.assertEqual("UNCERTAIN", lookup(reverse, 1000, 1002)["status"])
        self.assertEqual(0, lookup(reverse, 1000, 1006)["audio_start_ms"])
        clock = aligned("o’clock rang", "o", "'clock", "rang")
        self.assertEqual(1, clock["summary"]["normalized_matches"])
        self.assertEqual(0, lookup(clock, 1000, 1007)["audio_start_ms"])

    def test_omitted_source_word_gets_no_audio_time(self):
        result = aligned("one two three", "one", "three")
        self.assertEqual(1, result["summary"]["possible_omissions"])
        missing = next(op for op in result["operations"] if op["lexical_relation"] == "omission")
        self.assertIsNone(missing["audio_start_ms"])
        self.assertEqual("UNCERTAIN", lookup(result, 1004, 1007)["status"])

    def test_extra_asr_word_is_recorded_and_blocks_broad_lookup(self):
        result = aligned("one two", "one", "extra", "two")
        self.assertEqual(1, result["summary"]["asr_additions"])
        self.assertEqual("UNCERTAIN", lookup(result, 1000, 1007)["status"])

    def test_repeated_word_has_multiple_optimal_assignments(self):
        result = aligned("go go", "go")
        self.assertEqual(2, result["summary"]["ambiguous_source_tokens"])
        self.assertEqual(1, len(result["summary"]["ambiguous_regions"]))
        self.assertIsNone(lookup(result, 1000, 1002)["audio_start_ms"])

    def test_substitution_and_hyphen_dash(self):
        result = aligned("red blue", "red", "green")
        self.assertEqual(1, result["summary"]["substitutions"])
        self.assertEqual("UNCERTAIN", lookup(result, 1004, 1008)["status"])
        hyphen = aligned("well-known—yes", "well", "known", "yes")
        self.assertEqual(1, hyphen["summary"]["normalized_matches"])
        self.assertEqual(0, lookup(hyphen, 1000, 1010)["audio_start_ms"])

    def test_word_split_and_punctuation_only_are_rejected(self):
        result = aligned("Hello, world!", "Hello", "world")
        self.assertEqual("UNCERTAIN", lookup(result, 1001, 1005)["status"])
        self.assertEqual("UNCERTAIN", lookup(result, 1005, 1006)["status"])


if __name__ == "__main__":
    unittest.main()
