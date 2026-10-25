from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE, NAME_TOKEN_RE, signer_re


ACTION_RE = r"(?:EXONERA|EXONERAR|NOMEIA|NOMEAR)"
ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,5000}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNA|DESIGNAR|DISPENSA|DISPENSAR|RETIFICA|RESOLVE)\b|$)",
    re.I | re.S,
)

NAME = rf"{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,12}}?"
DIRECT_NAME_RE = re.compile(
    rf"(?:^|[,;:]\s*|\b(?:servidor(?:a)?|funcion[aá]rio(?:a)?|candidato(?:a)?|militar)\s+)"
    rf"(?!(?:a\s+pedido|por\s+necessidade\s+do\s+servi[cç]o)\b)"
    rf"(?P<name>{NAME})(?=\s*(?:,|matr[ií]cula|RG\b|CPF\b|do\s+cargo|para\s+|cargo\b|\d[\d./-]{{4,}}))",
    re.I,
)
NAME_AFTER_ACTION_RE = DIRECT_NAME_RE
TABLE_NAME_RE = re.compile(
    rf"(?:^|:\s*)\s*(?:\d+\.\s*)?(?:(?:CB|SD|SGT|3ºSGT|2ºSGT|1ºSGT|ST|TEN|CAP|CEL|MAJ|SOLD|BM)\s+){{0,3}}(?P<name>{NAME})"
    rf"\s+(?P<id>\d[\d./-]{{4,}})\s*$",
    re.I | re.M,
)

ROLE_RE = re.compile(
    r"(?:cargo(?:\s+efetivo)?\s+de|função\s+de|funcao\s+de|para\s+exercer\s+(?:o\s+)?cargo\s+de|"
    r"desempenhar\s+a\s+função\s+de|desempenhar\s+a\s+funcao\s+de)\s+"
    r"(?P<role>[^,.;\n]{2,220})",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:lotad[oa]\s+(?:na|no|em)?\s*|da|do|na|no)\s*"
    r"(?P<agency>(?:Secretaria|Secretaria de Estado|Fundação|Fundacao|Instituto|Universidade|"
    r"Polícia|Policia|Departamento|Defensoria|Procuradoria|Tribunal|Assembleia)[^,.;\n]{0,180})",
    re.I,
)
FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:matr[ií]cula|identifica[cç][aã]o\s+funcional)\s*"
    r"(?:n[º°.]?\s*)?(?P<id>[\d./-]+)",
    re.I,
)

SIGNER_CATEGORIES = [
    ("1", "Governador", r"Governador(?:a)?(?!\s+em\s+exerc)"),
    ("2", "Governador em exercicio", r"Governador(?:a)?\s+em\s+exerc[ií]cio"),
    ("4", "Secretario de Estado", r"Secret[aá]ri[oa]\s+de\s+Estado"),
    ("5", "Secretario", r"Secret[aá]ri[oa]"),
    ("6", "Presidente", r"Presidente"),
    ("8", "Diretor", r"Diretor[a]?") ,
]
SIGNER_RE = signer_re(SIGNER_CATEGORIES)
