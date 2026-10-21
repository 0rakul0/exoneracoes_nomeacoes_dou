from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE
from diarios_oficiais.utils_regex.common import NAME_TOKEN_RE
from diarios_oficiais.utils_regex.common import signer_re


ACTION_RE = r"(?:EXONERA|EXONERAR|NOMEIA|NOMEAR)"

ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,2400}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNA|NOMEIA|EXONERA|RETIFICA|RESOLVE)\b|$)",
    re.I | re.S,
)

BEFORE_ACTION_NAME_RE = re.compile(
    rf"\bNOME\s*:\s*(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s+IDENTIFICAÇÃO|\s+IDENTIFICACAO|\s+RG\b|\s+CPF\b)",
    re.I,
)

DIRECT_NAME_RE = re.compile(
    rf"\b(?:o\s+)?(?:Cap\s+PM\s+|Dr\.\s+|Dra\.\s+)?"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,|\s+ID\.?\s*(?:FUNC)?\b)",
    re.I,
)

NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:\b(?:servidor(?:a)?|funcion[aá]rio(?:s)?|candidato(?:a)?)\s+|"
    rf"\b(?:o|a)\s+(?:Cap\s+PM\s+|Dr\.\s+|Dra\.\s+)?)"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,|\s+ID\.?\s*(?:FUNC)?\b|\s+para\b)",
    re.I,
)

ROLE_RE = re.compile(
    r"(?:encargos de|cargo(?:/função)?|função de|como|do cargo de|da função de)\s+"
    r"(?P<role>[^,.;\n]{2,220})",
    re.I,
)

AGENCY_RE = re.compile(
    r"\b(?:na|no|nas|nos|da|do|das|dos|lotação:\s*)\s*"
    r"(?:Secretaria|Departamento|Fundação|Instituto|Polícia|Brigada|"
    r"Casa Civil|Casa Militar|Governo|Estado|SEDAC|SSPS|SEDUC|SES|SESP|"
    r"SPGG|DETRAN|DAER|FEPAM|IPE|PROCERGS)"
    r"(?:[^,.;\n]{0,220})",
    re.I,
)

FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:IDENTIFICAÇÃO|IDENTIFICACAO)\s+FUNCIONAL(?:/VÍNCULO|/VINCULO)?\s*:\s*"
    r"(?P<id>[\d./-]+)",
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
