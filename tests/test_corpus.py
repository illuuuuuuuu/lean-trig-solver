from pathlib import Path
import tempfile
import unittest

from lean_trig_solver.corpus import LeanCorpus, parse_declarations, tokenize


class CorpusTests(unittest.TestCase):
    def test_parse_multiple_declarations(self) -> None:
        text = """theorem sine_even (x : ℝ) : True := by trivial

def phase (x : ℝ) := x
"""
        declarations = parse_declarations(Path("Sample.lean"), text)
        self.assertEqual([item.name for item in declarations], ["sine_even", "phase"])

    def test_search_prefers_matching_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Trig.lean"
            path.write_text(
                """theorem sine_addition : True := by trivial

theorem cosine_periodicity : True := by trivial
""",
                encoding="utf-8",
            )
            corpus = LeanCorpus.from_paths([path])
            hits = corpus.search("prove a sine addition identity", limit=1)
            self.assertEqual(hits[0].declaration.name, "sine_addition")

    def test_identifier_aliases(self) -> None:
        self.assertIn("sin", tokenize("sineFunction"))


if __name__ == "__main__":
    unittest.main()

