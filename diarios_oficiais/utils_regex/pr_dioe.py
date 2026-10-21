from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE
from diarios_oficiais.utils_regex.common import NAME_TOKEN_RE
from diarios_oficiais.utils_regex.common import signer_re


ACTION_RE = r"(?:EXONERAR|NOMEAR)"

ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,7000}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNAR|DESIGNADO|CESSAR|TORNAR\s+SEM\s+EFEITO|"
    rf"RESOLVE|RETIFICA(?:R|ÇÃO)?)\b|$)",
    re.I | re.S,
)

NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*|\b(?:a|o|as|os)(?:\(s\))?\s+"
    rf"(?:servidor(?:a)?|funcion[aá]rio(?:s)?|candidato(?:\(a\))?)\s+|"
    rf"\bS(?:R|RA)\.?\s+|"
    rf"\b(?:servidor(?:a)?|funcion[aá]rio(?:s)?|candidato(?:\(a\))?|"
    rf"a|o|as|os)(?:\(s\))?\s+)"
    rf"(?:abaixo\s+relacionad[oa](?:\(s\))?\s*:\s*)?"
    rf"(?:matr[ií]cula\s+)?(?:[\d./-]+\s+)?"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,|\s+(?:para|p/|do|da|no|na|n[º°o.]|matr[ií]cula|"
    rf"v[ií]nculo|ocupante|cargo|lotad[oa]|a\s+partir|órgão|orgao)\b)",
    re.I,
)

# The SEAP personnel extracts use a compact table: NAME, RG, LF, CARGO,
# PROTOCOLO, A PARTIR, ORGAO. One EXONERAR/NOMEAR verb can therefore cover
# several people; parse_acts expands this pattern into one Act per row.
MULTI_NAME_RE = re.compile(
    rf"(?:\b(?:PARTIR\s+ORGAO|SEED|SEAP|SESP|SEFA|PGE|CRE)\s+)?"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s+\d[\d.\-/]*\s+\d{{1,3}}\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ�])",
    re.I,
)

DIRECT_NAME_RE = re.compile(
    rf"\bS(?:R|RA)\.?\s+(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,)",
    re.I,
)

MULTI_NAME_TRIGGER_RE = re.compile(
    r"\b(?:NOME\s+RG\s+LF|FUNCION[AÁ]RIOS\s+ABAIXO\s+RELACIONADOS)\b",
    re.I,
)

NAME_PREFIX_BLACKLIST = {
    "A",
    "AS",
    "CARGO",
    "CONSIDERANDO",
    "CRE",
    "DEPARTAMENTO",
    "DESTINADA",
    "DIRETOR",
    "DIRETORA",
    "ESTADO",
    "NOME",
    "NOMEADA",
    "NOMEADO",
    "ORGAO",
    "ÓRGÃO",
    "PARANA",
    "PARTIR",
    "PGE",
    "PORTARIA",
    "SEAP",
    "SEED",
    "SEFA",
    "SESP",
}

ROLE_RE = re.compile(
    r"(?:para exercer|ocupante do|ocupante de|do|da|no|na|em)\s+"
    r"(?:o\s+|a\s+)?(?P<role>(?:cargo(?:\s+de|\s+em\s+comiss[aã]o)?|"
    r"fun[cç][aã]o|emprego|chefia|dire[cç][aã]o|assessoria|classe|carreira)"
    r"[^,.;\n]{0,260})",
    re.I,
)

AGENCY_RE = re.compile(
    r"\b(?:da|do|na|no)\s+(?:Secretaria|Subsecretaria|"
    r"Procuradoria|Superintend[eê]ncia|Instituto|Departamento|Gabinete|"
    r"Funda[cç][aã]o|Autarquia|Universidade|Pol[ií]cia|Hospital|"
    r"DETRAN|DER|SEAP|SEED|SESP|SEFA|PGE|PRPREV)"
    r"(?:[^,.;\n]{0,220})",
    re.I,
)

FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:MATR[IÍ]CULA|ID\s+FUNCIONAL|N[º°O.]?\s*FUNCIONAL)\s*"
    r"(?:N[º°O.]*)?\s*[:.]?\s*(?P<id>[\d.Xx.\-/]+)",
    re.I,
)

SIGNER_CATEGORIES = [
    ("1", "Governador", r"Governador(?:a)?(?!\s+em\s+exerc)"),
    ("2", "Governador em exercicio", r"Governador(?:a)?\s+em\s+exerc[ií]cio"),
    ("3", "Diretor-Presidente", r"Diretor(?:a)?\s*[-–]\s*Presidente"),
    ("4", "Secretario de Estado", r"Secret[aá]ri[oa]\s+de\s+Estado(?:[^.;\n]{0,100})?"),
    ("5", "Secretario", r"Secret[aá]ri[oa](?:[^.;\n]{0,80})?"),
    ("6", "Presidente", r"Presidente(?:[^.;\n]{0,80})?"),
    ("7", "Diretor-Geral", r"Diretor[a]?\s*[-–]\s*Geral|Diretor[a]?\s+Geral"),
    ("8", "Diretor", r"Diretor[a]?(?:[^.;\n]{0,80})?"),
    ("9", "Subsecretario", r"Subsecret[aá]ri[oa](?:[^.;\n]{0,100})?"),
    ("10", "Superintendente", r"Superintendente(?:[^.;\n]{0,100})?"),
    ("11", "Chefe de Gabinete", r"Chefe\s+de\s+Gabinete"),
    ("12", "Coordenador", r"Coordenador[a]?(?:[^.;\n]{0,80})?"),
]

SIGNER_RE = signer_re(SIGNER_CATEGORIES)
