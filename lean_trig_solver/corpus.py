from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Iterable, Sequence


DECLARATION_RE = re.compile(
    r"(?m)^(?:private\s+|protected\s+)?"
    r"(?P<kind>theorem|lemma|def|abbrev|structure)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_']*|[\u0370-\u03ff]+")


@dataclass(frozen=True)
class LeanDeclaration:
    path: Path
    kind: str
    name: str
    text: str

    @property
    def statement(self) -> str:
        for marker in (":= by", ":=\nby", " where"):
            if marker in self.text:
                return self.text.split(marker, 1)[0].rstrip()
        return self.text.rstrip()


@dataclass(frozen=True)
class SearchHit:
    declaration: LeanDeclaration
    score: float


def _split_identifier(value: str) -> list[str]:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return [part.lower() for part in re.split(r"[_']+|\s+", value) if part]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in WORD_RE.findall(text):
        tokens.extend(_split_identifier(match))
    aliases = {
        "sine": "sin",
        "cosine": "cos",
        "tangent": "tan",
        "alpha": "α",
        "beta": "β",
        "theta": "θ",
    }
    return [aliases.get(token, token) for token in tokens if len(token) > 1]


def parse_declarations(path: Path, text: str) -> list[LeanDeclaration]:
    matches = list(DECLARATION_RE.finditer(text))
    declarations: list[LeanDeclaration] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.start() : end].strip()
        declarations.append(
            LeanDeclaration(
                path=path,
                kind=match.group("kind"),
                name=match.group("name"),
                text=block,
            )
        )
    return declarations


def lean_files(paths: Iterable[Path]) -> list[Path]:
    found: set[Path] = set()
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if path.is_file() and path.suffix == ".lean":
            found.add(path)
        elif path.is_dir():
            for candidate in path.rglob("*.lean"):
                if ".lake" not in candidate.parts:
                    found.add(candidate.resolve())
    return sorted(found)


class LeanCorpus:
    def __init__(self, declarations: Sequence[LeanDeclaration]):
        self.declarations = list(declarations)
        self._tokens = [Counter(tokenize(item.text)) for item in self.declarations]
        self._document_frequency: Counter[str] = Counter()
        for token_counts in self._tokens:
            self._document_frequency.update(token_counts.keys())

    @classmethod
    def from_paths(cls, paths: Iterable[Path]) -> "LeanCorpus":
        declarations: list[LeanDeclaration] = []
        for path in lean_files(paths):
            declarations.extend(parse_declarations(path, path.read_text(encoding="utf-8")))
        return cls(declarations)

    def search(self, query: str, limit: int = 8) -> list[SearchHit]:
        if limit <= 0 or not self.declarations:
            return []
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []
        total = len(self.declarations)
        hits: list[SearchHit] = []
        for declaration, document_tokens in zip(self.declarations, self._tokens):
            score = 0.0
            for token, query_count in query_tokens.items():
                document_count = document_tokens.get(token, 0)
                if not document_count:
                    continue
                frequency = self._document_frequency[token]
                inverse_document_frequency = math.log((total + 1) / (frequency + 1)) + 1
                score += min(query_count, 2) * (1 + math.log(document_count)) * inverse_document_frequency
            name_tokens = set(tokenize(declaration.name))
            score += 1.5 * len(name_tokens.intersection(query_tokens))
            if score > 0:
                hits.append(SearchHit(declaration=declaration, score=score))
        hits.sort(key=lambda hit: (-hit.score, hit.declaration.name))
        return hits[:limit]

