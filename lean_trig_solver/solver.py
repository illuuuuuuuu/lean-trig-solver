from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable

from .corpus import LeanCorpus, SearchHit
from .providers import ProofProvider
from .verifier import LeanVerifier, VerificationResult


PLACEHOLDER_RE = re.compile(
    r":=\s*by\s*(?:\n\s*)?(?:sorry|admit)\b|:=\s*(?:sorry|admit)\b",
    re.MULTILINE,
)
FENCE_RE = re.compile(r"```(?:lean|lean4)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


DETERMINISTIC_PROOFS = (
    "by\n  simp",
    "by\n  ring",
    "by\n  ring_nf",
    "by\n  linarith",
    "by\n  nlinarith",
    "by\n  positivity",
    "by\n  aesop",
    "by\n  simpa [pow_two] using Real.sin_sq_add_cos_sq _",
    "by\n  simp [Real.sin_add, Real.sin_sub, Real.cos_add, Real.cos_sub]\n  <;> ring",
)


SYSTEM_PROMPT = """You are a Lean 4 proof engineer specialized in real trigonometry.
Return exactly one Lean proof term beginning with `by`. Do not return a theorem
declaration, Markdown, explanations, `sorry`, `admit`, or new axioms. Prefer
stable Mathlib lemmas and short auditable tactics. Respect every side condition.
The candidate will be compiled by Lean; compiler feedback may be provided for a
repair attempt."""


@dataclass(frozen=True)
class Attempt:
    source: str
    proof: str
    ok: bool
    feedback: str


@dataclass
class SolveResult:
    ok: bool = False
    proof: str | None = None
    verified_source: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    retrieved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "proof": self.proof,
            "verified_source": self.verified_source,
            "attempts": [asdict(attempt) for attempt in self.attempts],
            "retrieved": self.retrieved,
        }


def extract_proof(model_text: str) -> str:
    candidates = FENCE_RE.findall(model_text)
    text = candidates[0].strip() if candidates else model_text.strip()
    if ":=" in text:
        text = text.rsplit(":=", 1)[1].strip()
    match = re.search(r"(?m)^\s*by\b", text)
    if match:
        text = text[match.start() :].strip()
    if not text.startswith("by"):
        raise ValueError("Model output did not contain a proof beginning with `by`")
    return text


def render_problem(problem_source: str, proof: str) -> str:
    matches = list(PLACEHOLDER_RE.finditer(problem_source))
    if len(matches) != 1:
        raise ValueError(
            "Problem file must contain exactly one placeholder written as `:= by sorry`."
        )
    return PLACEHOLDER_RE.sub(":= " + proof.strip(), problem_source, count=1)


def _format_context(hits: Iterable[SearchHit], max_chars: int = 18000) -> str:
    sections: list[str] = []
    used = 0
    for hit in hits:
        block = (
            f"-- {hit.declaration.name} ({hit.declaration.path.name})\n"
            f"{hit.declaration.text.strip()}"
        )
        if used + len(block) > max_chars:
            break
        sections.append(block)
        used += len(block)
    return "\n\n".join(sections) or "-- No retrieved examples"


def _user_prompt(
    problem_source: str,
    hits: list[SearchHit],
    previous_proof: str | None,
    feedback: str | None,
) -> str:
    parts = [
        "Prove the single placeholder in this Lean file:",
        "```lean\n" + problem_source.strip() + "\n```",
        "Potentially relevant verified declarations:",
        "```lean\n" + _format_context(hits) + "\n```",
    ]
    if previous_proof and feedback:
        parts.extend(
            [
                "The previous candidate failed:",
                "```lean\n" + previous_proof + "\n```",
                "Lean feedback:",
                "```text\n" + feedback[-6000:] + "\n```",
                "Repair the proof. Return only the replacement proof beginning with `by`.",
            ]
        )
    return "\n\n".join(parts)


class TrigSolver:
    def __init__(
        self,
        verifier: LeanVerifier,
        corpus: LeanCorpus,
        provider: ProofProvider | None,
    ):
        self.verifier = verifier
        self.corpus = corpus
        self.provider = provider

    def _try(self, problem_source: str, proof: str, source: str) -> tuple[Attempt, str]:
        verified_source = render_problem(problem_source, proof)
        result: VerificationResult = self.verifier.verify(verified_source)
        attempt = Attempt(
            source=source,
            proof=proof,
            ok=result.ok,
            feedback="" if result.ok else result.feedback,
        )
        return attempt, verified_source

    def solve(
        self,
        problem_source: str,
        *,
        model_attempts: int = 4,
        top_k: int = 8,
        use_deterministic: bool = True,
    ) -> SolveResult:
        render_problem(problem_source, "by\n  trivial")
        hits = self.corpus.search(problem_source, limit=top_k)
        result = SolveResult(retrieved=[hit.declaration.name for hit in hits])

        if use_deterministic:
            for proof in DETERMINISTIC_PROOFS:
                attempt, verified_source = self._try(problem_source, proof, "deterministic")
                result.attempts.append(attempt)
                if attempt.ok:
                    result.ok = True
                    result.proof = proof
                    result.verified_source = verified_source
                    return result

        if self.provider is None:
            return result

        previous_proof: str | None = None
        feedback: str | None = None
        for _ in range(max(model_attempts, 0)):
            prompt = _user_prompt(problem_source, hits, previous_proof, feedback)
            try:
                model_text = self.provider.generate(SYSTEM_PROMPT, prompt)
                proof = extract_proof(model_text)
            except Exception as error:
                result.attempts.append(
                    Attempt("model", "", False, f"Model generation failed: {error}")
                )
                break
            attempt, verified_source = self._try(problem_source, proof, "model")
            result.attempts.append(attempt)
            if attempt.ok:
                result.ok = True
                result.proof = proof
                result.verified_source = verified_source
                return result
            previous_proof = proof
            feedback = attempt.feedback
        return result
