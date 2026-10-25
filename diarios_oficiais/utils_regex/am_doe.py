from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE, NAME_TOKEN_RE, signer_re

ACTION_RE = r"(?:EXONERA|EXONERAR|NOMEIA|NOMEAR)"
ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,5000}}?)(?=\b(?:{ACTION_RE}|DESIGNA|DESIGNAR|DISPENSA|DISPENSAR|RESOLVE)\b|$)",
    re.I | re.S,
)
NAME = rf"{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,12}}?"
DIRECT_NAME_RE = re.compile(
    rf"(?:^|[,;:]\s*|\b(?:servidor(?:a|es)?|funcion[aá]rio(?:a|s)?|candidato(?:a|s)?)\s*:?)\s*"
    rf"(?P<name>{NAME})(?=\s*(?:,|matr[ií]cula|RG\b|CPF\b|do\s+cargo|para\s+|cargo\b))",
    re.I,
)
NAME_AFTER_ACTION_RE = DIRECT_NAME_RE
ROLE_RE = re.compile(
    r"(?:cargo(?:\s+efetivo)?\s+de|função\s+de|funcao\s+de|para\s+exercer\s+(?:o\s+)?cargo\s+de)\s+(?P<role>[^,.;\n]{2,220})",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:lotad[oa]\s+(?:na|no|em)?\s*|da|do|na|no)\s*(?P<agency>(?:Secretaria|Secretaria de Estado|Fundação|Fundacao|Instituto|Universidade|Polícia|Policia|Departamento|Defensoria|Procuradoria)[^,.;\n]{0,180})",
    re.I,
)
FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:matr[ií]cula(?:\s+funcional)?|identifica[cç][aã]o\s+funcional)\s*(?:n[º°.]?\s*)?(?P<id>[\d./-]+)",
    re.I,
)
SIGNER_CATEGORIES = [("1", "Governador", r"Governador(?:a)?"), ("4", "Secretario de Estado", r"Secret[aá]ri[oa]\s+de\s+Estado"), ("5", "Secretario", r"Secret[aá]ri[oa]")]
SIGNER_RE = signer_re(SIGNER_CATEGORIES)
