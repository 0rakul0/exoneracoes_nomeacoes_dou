from __future__ import annotations

import re


DATE_LINK_RE = re.compile(r'href=["\']do_seleciona_edicao\.php\?data=([^"\']+)["\']', re.I)
EDITION_LINK_RE = re.compile(
    r'<a\s+href=["\'](?P<href>mostra_edicao\.php\?session=[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
PDF_KEY_RE = re.compile(r'var\s+pd\s*=\s*["\'](?P<key>[A-F0-9-]+)["\']', re.I)

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")

UPPER_PT = "A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00c2\u00ca\u00d4\u00c3\u00d5\u00c7"
WORD_PT = r"\w\u00c1\u00c9\u00cd\u00d3\u00da\u00c2\u00ca\u00d4\u00c3\u00d5\u00c7.'-"
NAME_TOKEN_RE = rf"[{UPPER_PT}][{WORD_PT}]+"

ACT_WINDOW_RE = re.compile(
    r"\b(?P<action>EXONERAR|NOMEAR)\b(?P<body>.{0,1200}?)(?=\b(?:EXONERAR|NOMEAR|DESIGNAR|TORNAR SEM EFEITO|RESOLVE|DECRETO|ATO DO|SECRETARIA|Art\.|$))",
    re.I | re.S,
)
NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*)(?P<name>{NAME_TOKEN_RE}(?:\s+(?:DE|DA|DO|DAS|DOS|E|{NAME_TOKEN_RE})){{1,9}})(?=,|\s+para\s+|\s+do\s+|\s+da\s+)",
    re.I,
)
ROLE_RE = re.compile(
    r"(?:para exercer|do|da)\s+(?:o\s+|a\s+)?(?P<role>cargo(?:\s+em\s+comiss[a\u00e3]o)?|funcao|fun\u00e7\u00e3o|emprego|chefia|direcao|dire\u00e7\u00e3o|assessoria)[^,.;\n]{0,220}",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:da|do)\s+(Secretaria|Subsecretaria|Fundacao|Funda\u00e7\u00e3o|Instituto|Departamento|Gabinete|Superintendencia|Superintend\u00eancia|Autarquia)\b[^,.;\n]{0,180}",
    re.I,
)
FUNCTIONAL_ID_RE = re.compile(
    r"\bID\s+FUNCIONAL\s*(?:N[\u00ba\u00b0O.]*)?\s*(?P<id>[\d.\-/]+)",
    re.I,
)

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
SIGNER_RE = re.compile(
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+(?:DE|DA|DO|DAS|DOS|E|{NAME_TOKEN_RE})){{1,8}})\s+(?P<role>"
    + "|".join(f"(?:{pattern})" for _, _, pattern in SIGNER_CATEGORIES)
    + r")\b",
    re.I,
)
