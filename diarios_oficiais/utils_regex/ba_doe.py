from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE
from diarios_oficiais.utils_regex.common import NAME_TOKEN_RE
from diarios_oficiais.utils_regex.common import signer_re


# O HTML do DOE/BA registra atos tanto no infinitivo quanto em formas como
# "considerar exonerado" e "nomeado".
ACTION_RE = r"(?:EXONER(?:A|AR|AD[AO]S?)|NOME(?:IA|AR|AD[AO]S?))"

ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,2200}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNAR|DESIGNADO|CESSAR|TORNAR\s+SEM\s+EFEITO|"
    rf"RESOLVE|DECRETO|PORTARIA|RETIFICA(?:R|ÇÃO)?|Art\.)\b|$)",
    re.I | re.S,
)

NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*|\b(?:a|o|as|os)(?:\(s\))?\s+(?:servidor(?:\(es\)|a)?|candidato(?:\(a\))?)\s+|"
    rf"\b(?:servidor(?:\(es\)|a)?|candidato(?:\(a\))?|a|o|as|os)(?:\(s\))?\s+)"
    rf"(?:abaixo\s+relacionad[oa](?:\(s\))?\s*:\s*)?"
    rf"(?:matr[ií]cula\s+)?(?:[\d./-]+\s+)?"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,|\s+(?:para|p/|do|da|no|na|n[º°o.]|matr[ií]cula|"
    rf"v[ií]nculo|ocupante|cargo|fun[cç][aã]o|lotad[oa]|a\s+partir|"
    rf"coordenador|diretor|assessor|secret[aá]rio|professor|gerente)\b)",
    re.I,
)

# Nas portarias de RHBAHIA, o HTML textualizado fica no formato
# "matricula NOME cargo". O primeiro nome da linha é a melhor evidencia
# disponivel para o ato coletivo.
TABLE_NAME_RE = re.compile(
    rf"\b\d{{5,}}\s+(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s+(?:Assessor|Assistente|Agente|Analista|Coordenador|Diretor|Gerente|"
    rf"Professor|Tecnico|T[eé]cnico|Especialista|Auxiliar|Auditor|Fiscal|Cargo)\b)",
    re.I,
)

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
    r"DETRAN|DPT|SAEB|SEFAZ|SESAB|SEC|SSP|PGE|EGBA)"
    r"(?:[^,.;\n]{0,220})",
    re.I,
)

FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:ID\s+FUNCIONAL|N[º°O.]?\s*FUNCIONAL|"
    r"MATR[IÍ]CULA(?:\s+FUNCIONAL)?)\s*"
    r"(?:N[º°O.]*)?\s*[:.]?\s*(?P<id>[\d.Xx.\-/]+)",
    re.I,
)


SIGNER_CATEGORIES = [
    ("1", "Governador", r"Governador(?:a)?(?!\s+em\s+exerc)"),
    ("2", "Governador em exercicio", r"Governador(?:a)?\s+em\s+exerc[ií]cio"),
    ("3", "Diretor-Presidente", r"Diretor(?:a)?\s*-\s*Presidente"),
    ("4", "Secretario de Estado", r"Secret[aá]ri[oa]\s+de\s+Estado(?:[^.;\n]{0,100})?"),
    ("5", "Secretario", r"Secret[aá]ri[oa](?:[^.;\n]{0,80})?"),
    ("6", "Presidente", r"Presidente(?:[^.;\n]{0,80})?"),
    ("7", "Diretor-Geral", r"Diretor[a]?\s*-\s*Geral|Diretor[a]?\s+Geral"),
    ("8", "Diretor", r"Diretor[a]?(?:[^.;\n]{0,80})?"),
    ("9", "Subsecretario", r"Subsecret[aá]ri[oa](?:[^.;\n]{0,100})?"),
    ("10", "Superintendente", r"Superintendente(?:[^.;\n]{0,100})?"),
    ("11", "Chefe de Gabinete", r"Chefe\s+de\s+Gabinete"),
    ("12", "Coordenador", r"Coordenador[a]?(?:[^.;\n]{0,80})?"),
]

SIGNER_RE = signer_re(SIGNER_CATEGORIES)
