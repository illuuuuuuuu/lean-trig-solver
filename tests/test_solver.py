import unittest

from lean_trig_solver.solver import extract_proof, render_problem


class SolverTests(unittest.TestCase):
    def test_extract_fenced_proof(self) -> None:
        self.assertEqual(
            extract_proof("```lean\nby\n  ring\n```"),
            "by\n  ring",
        )

    def test_extract_proof_from_declaration(self) -> None:
        self.assertEqual(
            extract_proof("theorem example : True := by\n  trivial"),
            "by\n  trivial",
        )

    def test_render_replaces_exactly_one_placeholder(self) -> None:
        source = "import Mathlib\n\ntheorem example : True := by\n  sorry\n"
        rendered = render_problem(source, "by\n  trivial")
        self.assertNotIn("sorry", rendered)
        self.assertIn(":= by\n  trivial", rendered)

    def test_render_rejects_missing_placeholder(self) -> None:
        with self.assertRaises(ValueError):
            render_problem("theorem example : True := by trivial", "by trivial")


if __name__ == "__main__":
    unittest.main()

