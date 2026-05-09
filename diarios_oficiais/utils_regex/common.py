from __future__ import annotations

import re


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

UPPER_PT = "A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00c2\u00ca\u00d4\u00c3\u00d5\u00c7"
WORD_PT = r"\w\u00c1\u00c9\u00cd\u00d3\u00da\u00c2\u00ca\u00d4\u00c3\u00d5\u00c7.'-"
NAME_TOKEN_RE = rf"[{UPPER_PT}][{WORD_PT}]+"
NAME_CONNECTOR_RE = rf"(?:DE|DA|DO|DAS|DOS|E|{NAME_TOKEN_RE})"


SIGNER_CATEGORIES = [
    ("1", "Governador", r"Governador(?!\s+em\s+exerc)"),
    ("2", "Governador em exercicio", r"Governador\s+em\s+exerc[\u00edi]cio"),
    ("3", "Diretor-Presidente", r"Diretor\s*-\s*Presidente|Diretor-Presidente"),
    ("4", "Secretario de Estado", r"Secret[\u00e1a]rio\s+de\s+Estado"),
    ("5", "Secretario", r"Secret[\u00e1a]rio"),
    ("6", "Presidente", r"Presidente"),
    ("7", "Diretor-Geral", r"Diretor\s*-\s*Geral|Diretor-Geral"),
    ("8", "Diretor", rf"Diretor(?:a)?(?:\s+{NAME_TOKEN_RE}){{0,3}}"),
    ("9", "Subsecretario", r"Subsecret[\u00e1a]rio"),
    ("10", "Superintendente", r"Superintendente"),
    ("11", "Chefe de Gabinete", r"Chefe\s+de\s+Gabinete"),
    ("12", "Coordenador", r"Coordenador(?:a)?"),
]


def signer_re(categories: list[tuple[str, str, str]] | None = None) -> re.Pattern[str]:
    categories = categories or SIGNER_CATEGORIES
    return re.compile(
        rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,8}})\s+(?P<role>"
        + "|".join(f"(?:{pattern})" for _, _, pattern in categories)
        + r")\b",
        re.I,
    )
