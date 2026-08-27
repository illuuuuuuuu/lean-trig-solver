from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .corpus import LeanCorpus
from .providers import ProviderError, build_provider
from .solver import TrigSolver
from .verifier import LeanVerifier


def _library_paths(values: list[str]) -> list[Path]:
    paths = [Path(value) for value in values]
    configured = os.environ.get("TRIG_SOLVER_LIBRARY", "")
    paths.extend(Path(value) for value in configured.split(os.pathsep) if value)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lean-trig-solver",
        description="Generate trigonometric Lean proofs and accept only compiled candidates.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index = subparsers.add_parser("index", help="Inspect an external Lean corpus")
    index.add_argument("--library", action="append", default=[], required=True)

    solve = subparsers.add_parser("solve", help="Solve one `:= by sorry` placeholder")
    solve.add_argument("problem", type=Path)
    solve.add_argument("--lean-project", type=Path, default=Path.cwd())
    solve.add_argument("--library", action="append", default=[])
    solve.add_argument(
        "--provider",
        choices=("openai", "anthropic", "none"),
        default=os.environ.get("TRIG_SOLVER_PROVIDER", "none"),
    )
    solve.add_argument("--model")
    solve.add_argument("--attempts", type=int, default=4)
    solve.add_argument("--top-k", type=int, default=8)
    solve.add_argument("--no-deterministic", action="store_true")
    solve.add_argument("--output", type=Path)
    solve.add_argument("--report", type=Path)
    solve.add_argument("--timeout", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "index":
        corpus = LeanCorpus.from_paths(_library_paths(args.library))
        print(f"Indexed {len(corpus.declarations)} Lean declarations.")
        return 0

    problem_source = args.problem.read_text(encoding="utf-8")
    corpus = LeanCorpus.from_paths(_library_paths(args.library))
    try:
        provider = build_provider(args.provider, args.model)
    except ProviderError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    solver = TrigSolver(
        verifier=LeanVerifier(args.lean_project, timeout=args.timeout),
        corpus=corpus,
        provider=provider,
    )
    try:
        result = solver.solve(
            problem_source,
            model_attempts=args.attempts,
            top_k=args.top_k,
            use_deterministic=not args.no_deterministic,
        )
    except ValueError as error:
        print(f"Problem error: {error}", file=sys.stderr)
        return 2

    if args.report:
        args.report.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if result.ok and result.proof and result.verified_source:
        if args.output:
            args.output.write_text(result.verified_source, encoding="utf-8")
        print(result.proof)
        print(
            f"Verified after {len(result.attempts)} attempt(s); "
            f"retrieved {len(result.retrieved)} declaration(s).",
            file=sys.stderr,
        )
        return 0

    print(f"No verified proof after {len(result.attempts)} attempt(s).", file=sys.stderr)
    if result.attempts:
        print(result.attempts[-1].feedback, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

