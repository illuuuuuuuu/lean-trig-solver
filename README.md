# Lean Trig Solver

**Author: Illusix Liu**

Lean Trig Solver is an experimental, Lean-verified AI solver specialized in
trigonometry. It accepts a Lean theorem containing one `:= by sorry`
placeholder, retrieves relevant declarations from an external Lean library,
tries a small deterministic tactic portfolio, and can ask an AI model to repair
failed proofs. A result is accepted only after the pinned Lean compiler checks
it successfully.

External Lean corpora are optional runtime inputs and are not included in this
repository. A user may explicitly point the solver at one or more external
Lean directories when running it.

## Current scope

The first version solves **Lean-to-Lean** problems:

```text
Lean theorem with one proof placeholder
        -> retrieve relevant Lean declarations
        -> try deterministic tactics
        -> optionally ask an AI model
        -> compile with Lean
        -> repair from compiler feedback
        -> return only a verified proof
```

Natural-language-to-Lean translation is intentionally outside the first
version. It can be added later as a separate, independently evaluated stage.

## Safety and privacy

- API keys are read only from environment variables.
- `.env` files are ignored by Git.
- The solver rejects `sorry`, `admit`, and new `axiom` declarations.
- OpenAI requests set `store: false`.
- When a model provider is enabled, the problem statement and the retrieved
  Lean snippets are sent to that provider. Do not point the solver at private
  material unless you intend to transmit those selected snippets.

## Installation

Requirements:

- Python 3.11 or later
- Lean through `elan`, with the `lake` command available

From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
lake update
lake build
```

The Lean version and Mathlib revision are pinned in `lean-toolchain` and
`lakefile.toml`.

## Try the verifier without an API

The included example can be solved by the deterministic tactic portfolio:

```bash
lean-trig-solver solve examples/sine_square_identity.lean \
  --lean-project . \
  --provider none \
  --output /tmp/verified.lean
```

The command prints the proof and writes a complete, compilable Lean file to
`/tmp/verified.lean`.

## Use an external trigonometry library

Point to external files at runtime; they remain in their own repository:

```bash
lean-trig-solver index \
  --library /path/to/lean-trigonometry-library

lean-trig-solver solve problem.lean \
  --lean-project . \
  --library /path/to/lean-trigonometry-library \
  --provider openai \
  --model YOUR_MODEL_ID
```

Multiple `--library` arguments are allowed. The same paths can instead be set
in `TRIG_SOLVER_LIBRARY`, separated by `:` on macOS and Linux.

## Model providers

No provider is enabled by default. Select a provider and supply its official
model ID yourself so the project does not silently switch models.

OpenAI:

```bash
export OPENAI_API_KEY="..."
export TRIG_SOLVER_PROVIDER="openai"
export TRIG_SOLVER_MODEL="YOUR_MODEL_ID"
```

Anthropic:

```bash
export ANTHROPIC_API_KEY="..."
export TRIG_SOLVER_PROVIDER="anthropic"
export TRIG_SOLVER_MODEL="YOUR_MODEL_ID"
```

Never paste a real key into a tracked file, issue, commit, or screenshot.

## Honest evaluation

Do not evaluate the solver on the same theorem proofs supplied to retrieval.
Create a held-out set of new statements, keep their proofs unavailable to the
solver, and report at least:

- number of solved problems;
- pass@1 and pass@k;
- time and model calls per problem;
- the fixed Lean/Mathlib versions;
- whether external retrieval was enabled.

This prevents an existing theorem from being mistaken for a newly discovered
proof.

## Copyright

Copyright © 2026 Illusix Liu. All rights reserved.

This repository is publicly available for viewing and evaluation. No license is
granted to use, copy, modify, or redistribute its contents, except as permitted
by applicable law and GitHub's Terms of Service.
