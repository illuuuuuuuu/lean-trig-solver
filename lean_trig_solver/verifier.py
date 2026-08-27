from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import tempfile


FORBIDDEN_RE = re.compile(r"\b(sorry|admit)\b|^\s*axiom\b", re.MULTILINE)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int

    @property
    def feedback(self) -> str:
        text = (self.stdout + "\n" + self.stderr).strip()
        return text[-6000:] if text else "Lean rejected the candidate without diagnostics."


class LeanVerifier:
    def __init__(self, project_dir: Path, timeout: float = 60.0):
        self.project_dir = project_dir.expanduser().resolve()
        self.timeout = timeout

    def verify(self, source: str) -> VerificationResult:
        forbidden = FORBIDDEN_RE.search(source)
        if forbidden:
            return VerificationResult(
                ok=False,
                stdout="",
                stderr=f"Forbidden incomplete proof marker: {forbidden.group(0).strip()}",
                returncode=2,
            )
        try:
            with tempfile.TemporaryDirectory(prefix="lean-trig-solver-") as directory:
                candidate = Path(directory) / "Main.lean"
                candidate.write_text(source, encoding="utf-8")
                completed = subprocess.run(
                    ["lake", "env", "lean", str(candidate)],
                    cwd=self.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
        except FileNotFoundError:
            return VerificationResult(False, "", "The `lake` command was not found.", 127)
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout if isinstance(error.stdout, str) else ""
            stderr = error.stderr if isinstance(error.stderr, str) else ""
            return VerificationResult(False, stdout, stderr + "\nLean verification timed out.", 124)
        return VerificationResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )

