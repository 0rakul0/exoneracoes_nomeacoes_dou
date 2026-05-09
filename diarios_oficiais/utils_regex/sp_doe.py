from __future__ import annotations

import re

from diarios_oficiais.utils_regex.common import NAME_CONNECTOR_RE
from diarios_oficiais.utils_regex.common import NAME_TOKEN_RE
from diarios_oficiais.utils_regex.common import SIGNER_CATEGORIES
from diarios_oficiais.utils_regex.common import signer_re


ACT_WINDOW_RE = re.compile(
    r"\b(?P<action>EXONERA|EXONERAR|NOMEIA|NOMEAR)\b(?P<body>.{0,1500}?)(?=\b(?:EXONERA|EXONERAR|NOMEIA|NOMEAR|DESIGNA|CESSA|TORNA SEM EFEITO|RESOLVE|DECRETO|PORTARIA|RETIFICA|Art\.)|$)",
    re.I | re.S,
)
NAME_AFTER_ACTION_RE = re.compile(
    rf"(?:^|,\s*|\ba\s+|\bo\s+|\bservidor(?:a)?\s+)(?P<name>{NAME_TOKEN_RE}(?:\s+{NAME_CONNECTOR_RE}){{1,9}})(?=,|\s+para\s+|\s+do\s+|\s+da\s+|\s+RG\b)",
    re.I,
)
ROLE_RE = re.compile(
    r"(?:para exercer|do|da|no|na)\s+(?:o\s+|a\s+)?(?P<role>cargo(?:\s+em\s+comiss[a\u00e3]o)?|fun[c\u00e7][a\u00e3]o|emprego|chefia|dire[c\u00e7][a\u00e3]o|assessoria|classe|carreira)[^,.;\n]{0,240}",
    re.I,
)
AGENCY_RE = re.compile(
    r"\b(?:da|do|na|no)\s+(Secretaria|Subsecretaria|Fundacao|Funda\u00e7\u00e3o|Instituto|Departamento|Gabinete|Coordenadoria|Unidade Regional|Diretoria|Autarquia|Universidade)\b[^,.;\n]{0,200}",
    re.I,
)
FUNCTIONAL_ID_RE = re.compile(
    r"\b(?:ID\s+FUNCIONAL|RG|R\.G\.|CPF|RS|RF)\s*(?:N[\u00ba\u00b0O.]*)?[:.]?\s*(?P<id>[\d.Xx.\-/]+)",
    re.I,
)
SIGNER_RE = signer_re(SIGNER_CATEGORIES)
