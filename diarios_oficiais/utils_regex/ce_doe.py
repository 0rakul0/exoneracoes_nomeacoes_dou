from __future__ import annotations

import re

from diarios_oficiais.utils_regex import pb_doe as _base
from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE, NAME_TOKEN_RE


# O DOE/CE usa com frequência "RESOLVE," e atos nominais como
# "tornar sem efeito a nomeação", além do infinitivo tradicional.
ACTION_RE = r"(?:EXONER(?:A|AR|AD[AO]S?)|NOME(?:IA|AR|AD[AO]S?)|NOMEA(?:ÇÃO|ÇÕES))"
ACT_WINDOW_RE = re.compile(
    rf"\b(?P<action>{ACTION_RE})\b(?P<body>.{{0,2200}}?)(?="
    rf"\b(?:{ACTION_RE}|DESIGNAR|DESIGNADO|CESSAR|TORNAR\s+SEM\s+EFEITO|"
    rf"RESOLVE|DECRETO|PORTARIA|RETIFICA(?:R|ÇÃO)?|Art\.)\b|$)",
    re.I | re.S,
)

PERSON_PREFIX_RE = (
    r"(?:SOLDADO|CABO|SARGENTO|TENENTE|CAPITÃO|CAPITAO|MAJOR|CORONEL|"
    r"POLICIAL|MILITAR|SERVIDOR(?:A)?|CANDIDATO(?:A)?|PROFESSOR(?:A)?)"
    r"(?:\s+(?:QPBM|PMCE|CBMCE|PM|BM))?"
)

PERSON_DESCRIPTOR_RE = (
    rf"(?:candidat[oa]|servidor(?:a)?|militar(?:\s+estadual)?|"
    rf"{PERSON_PREFIX_RE})(?:\s+estadual)?"
)
DIRECT_NAME_RE = re.compile(
    rf"(?:\b(?:a|o|as|os|de|da|do)\s+{PERSON_DESCRIPTOR_RE}\s+|"
    rf"\bde\s+)(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,8}})"
    rf"(?=\s*,|\s+classific|\s+matr[ií]cula|\s+CPF|\s+para)\b",
    re.I,
)

NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*|\b(?:a|o|as|os|de|da|do)\s+)"
    rf"(?:a\s+pedido\s+)?(?:{PERSON_PREFIX_RE}\s+)?"
    rf"(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,10}})"
    rf"(?=\s*,|\s+(?:para|do|da|no|na|n[º°o.]|matr[ií]cula|"
    rf"v[ií]nculo|ocupante|cargo|fun[cç][aã]o|lotad[oa])\b)",
    re.I,
)

TABLE_NAME_RE = _base.TABLE_NAME_RE
ROLE_RE = _base.ROLE_RE
AGENCY_RE = _base.AGENCY_RE
FUNCTIONAL_ID_RE = _base.FUNCTIONAL_ID_RE
SIGNER_CATEGORIES = _base.SIGNER_CATEGORIES
SIGNER_RE = _base.SIGNER_RE

FALSE_PERSON_STARTS = {
    "COMPROMISSO",
    "MESMA",
    "PROVAS",
    "SUAS",
}
